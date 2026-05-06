import React, {
  useRef, useEffect, useState, useCallback, useMemo,
} from 'react';
import { Send, Square, Mic } from 'lucide-react';

const API = '';

function pickRecorderMime() {
  if (typeof MediaRecorder === 'undefined') return '';
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];
  for (const t of candidates) {
    try {
      if (MediaRecorder.isTypeSupported(t)) return t;
    } catch {
      /* ignore */
    }
  }
  return '';
}

/**
 * @param {'whisper' | 'browser' | 'off'} voiceInputMode
 *   whisper: MediaRecorder → POST /voice/transcribe (local faster-whisper)
 *   browser: Web Speech API (Chrome/Edge; audio may be processed by the vendor)
 */
export default function InputBar({
  onSend,
  isStreaming,
  onStop,
  voiceInputMode = 'off',
}) {
  const taRef = useRef(null);
  const [value, setValue] = useState('');
  const [recState, setRecState] = useState('idle'); // idle | recording | transcribing
  const [voiceError, setVoiceError] = useState(null);
  const [voiceHint, setVoiceHint] = useState('');

  const streamRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const recognitionRef = useRef(null);
  const browserFinalRef = useRef('');
  const browserInterimRef = useRef('');
  const aliveRef = useRef(true);

  const voiceEnabled = voiceInputMode !== 'off';

  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [value, voiceHint]);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
      try {
        streamRef.current?.getTracks().forEach((t) => t.stop());
      } catch { /* ignore */ }
      streamRef.current = null;
      try {
        const mr = mediaRecorderRef.current;
        if (mr && mr.state !== 'inactive') mr.stop();
      } catch { /* ignore */ }
      mediaRecorderRef.current = null;
      try {
        recognitionRef.current?.stop?.();
      } catch { /* ignore */ }
      recognitionRef.current = null;
    };
  }, []);

  const appendTranscript = useCallback((text) => {
    const t = (text || '').trim();
    if (!t) return;
    setValue((prev) => {
      if (!prev) return t;
      return /\s$/.test(prev) ? `${prev}${t}` : `${prev} ${t}`;
    });
  }, []);

  const stopWhisperRecording = useCallback(() => {
    const mr = mediaRecorderRef.current;
    if (mr && mr.state !== 'inactive') {
      try {
        mr.stop();
      } catch {
        /* ignore */
      }
    }
  }, []);

  const startWhisperRecording = useCallback(async () => {
    setVoiceError(null);
    setVoiceHint('');
    if (!navigator.mediaDevices?.getUserMedia) {
      setVoiceError('Microphone API not available in this browser.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = pickRecorderMime();
      const mr = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = async () => {
        const blob = new Blob(chunksRef.current, {
          type: mr.mimeType || 'audio/webm',
        });
        chunksRef.current = [];
        try {
          stream.getTracks().forEach((t) => t.stop());
        } catch { /* ignore */ }
        streamRef.current = null;
        mediaRecorderRef.current = null;

        if (!blob.size) {
          setRecState('idle');
          setVoiceError('No audio captured.');
          return;
        }

        setRecState('transcribing');
        try {
          const fd = new FormData();
          fd.append('file', blob, 'recording.webm');
          const r = await fetch(`${API}/voice/transcribe`, { method: 'POST', body: fd });
          const data = await r.json().catch(() => ({}));
          if (!r.ok) {
            throw new Error(data.error || `Transcription failed (${r.status})`);
          }
          if (aliveRef.current) appendTranscript(data.text || '');
        } catch (e) {
          if (aliveRef.current) setVoiceError(String(e.message || e));
        } finally {
          if (aliveRef.current) setRecState('idle');
        }
      };
      mediaRecorderRef.current = mr;
      mr.start();
      setRecState('recording');
    } catch (e) {
      setVoiceError(String(e.message || e));
      setRecState('idle');
    }
  }, [appendTranscript]);

  const stopBrowserRecognition = useCallback(() => {
    try {
      recognitionRef.current?.stop?.();
    } catch { /* ignore */ }
    recognitionRef.current = null;
  }, []);

  const startBrowserRecognition = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      setVoiceError('Speech recognition not supported.');
      return;
    }
    setVoiceError(null);
    setVoiceHint('');
    browserFinalRef.current = '';
    browserInterimRef.current = '';
    const rec = new SR();
    recognitionRef.current = rec;
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = 'en-GB';
    rec.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const piece = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          browserFinalRef.current += piece;
        } else {
          interim += piece;
        }
      }
      browserInterimRef.current = interim;
      setVoiceHint(interim);
    };
    rec.onerror = (ev) => {
      setVoiceError(ev.error || 'speech error');
      setRecState('idle');
      setVoiceHint('');
      browserInterimRef.current = '';
    };
    rec.onend = () => {
      recognitionRef.current = null;
      const joined = `${browserFinalRef.current} ${browserInterimRef.current}`.replace(/\s+/g, ' ').trim();
      browserFinalRef.current = '';
      browserInterimRef.current = '';
      if (!aliveRef.current) return;
      setVoiceHint('');
      if (joined) appendTranscript(joined);
      setRecState('idle');
    };
    try {
      rec.start();
      setRecState('recording');
    } catch (e) {
      setVoiceError(String(e.message || e));
      setRecState('idle');
    }
  }, [appendTranscript]);

  useEffect(() => {
    if (recState !== 'recording' || voiceInputMode !== 'browser') return undefined;
    const id = window.setTimeout(() => {
      try {
        recognitionRef.current?.stop?.();
      } catch { /* ignore */ }
    }, 120000);
    return () => window.clearTimeout(id);
  }, [recState, voiceInputMode]);

  const toggleMic = useCallback(() => {
    if (!voiceEnabled || isStreaming) return;
    if (recState === 'transcribing') return;

    if (recState === 'recording') {
      if (voiceInputMode === 'whisper') stopWhisperRecording();
      else stopBrowserRecognition();
      return;
    }

    if (voiceInputMode === 'whisper') startWhisperRecording();
    else startBrowserRecognition();
  }, [
    voiceEnabled,
    isStreaming,
    recState,
    voiceInputMode,
    startWhisperRecording,
    stopWhisperRecording,
    stopBrowserRecognition,
    startBrowserRecognition,
  ]);

  const handleSend = useCallback(() => {
    if (!value.trim() || isStreaming) return;
    onSend(value.trim());
    setValue('');
    if (taRef.current) taRef.current.style.height = 'auto';
  }, [value, isStreaming, onSend]);

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const canSend = value.trim().length > 0 && !isStreaming;
  const recording = recState === 'recording';
  const transcribing = recState === 'transcribing';

  const micTitle = useMemo(() => {
    if (!voiceEnabled) return 'Voice input unavailable (install faster-whisper + ffmpeg for local STT, or use Chrome/Edge for browser mode)';
    if (isStreaming) return 'Unavailable while JAR is responding';
    if (transcribing) return 'Transcribing…';
    if (recording) return 'Stop recording';
    if (voiceInputMode === 'whisper') return 'Record voice (local Whisper)';
    return 'Record voice (browser speech recognition)';
  }, [voiceEnabled, isStreaming, transcribing, recording, voiceInputMode]);

  return (
    <div className="input-container">
      <div className={`input-pill ${recording ? 'recording' : ''}`}>
        <textarea
          ref={taRef}
          className="input-textarea"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKey}
          placeholder={recording ? 'Listening…' : 'Ask JAR anything…'}
          rows={1}
          disabled={isStreaming || transcribing}
          id="chat-input"
        />

        {recording && voiceInputMode === 'browser' && voiceHint ? (
          <div className="input-voice-interim" aria-live="polite">{voiceHint}</div>
        ) : null}

        <div className="input-actions">
          <div className="input-left">
            <button
              type="button"
              className={`input-mic-btn ${recording ? 'active' : ''} ${transcribing ? 'transcribing' : ''}`}
              onClick={toggleMic}
              disabled={!voiceEnabled || isStreaming || transcribing}
              title={micTitle}
              id="voice-input-btn"
            >
              <Mic size={16} />
            </button>
          </div>

          <div className="input-right">
            {voiceError && (
              <span className="input-voice-err" title={voiceError}>
                Mic error
              </span>
            )}
            {isStreaming ? (
              <button className="send-btn stop" onClick={onStop} title="Stop" id="stop-btn" type="button">
                <Square size={14} fill="currentColor" />
              </button>
            ) : (
              <button className="send-btn" onClick={handleSend} disabled={!canSend} title="Send" id="send-btn" type="button">
                <Send size={15} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
