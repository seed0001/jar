import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Menu, Wifi, WifiOff } from 'lucide-react';
import Sidebar from './components/Sidebar.jsx';
import ChatWindow from './components/ChatWindow.jsx';
import InputBar from './components/InputBar.jsx';
import ModelSelector from './components/ModelSelector.jsx';
import VoiceSelector from './components/VoiceSelector.jsx';

const API = '';

const TIER_LABELS = ['', 'Express', 'Standard', 'Deep'];

/** Strip markdown-ish noise for TTS (plain text, length-capped). */
function plainForTts(raw) {
  if (!raw) return '';
  return String(raw)
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`[^`]+`/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/<[^>]+>/g, ' ')
    .replace(/[#>*_|~\-]{1,3}/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 48000);
}

export default function App() {
  const [sessions,       setSessions]      = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [messages,       setMessages]      = useState([]);
  const [isStreaming,    setIsStreaming]    = useState(false);
  const [sidebarOpen,    setSidebarOpen]   = useState(true);
  const [health,         setHealth]        = useState(null);
  const [tierModels,     setTierModels]     = useState({ 1: '', 2: '', 3: '' });
  const [ollamaModels,   setOllamaModels]   = useState([]);
  const [fallbackModel, setFallbackModel] = useState('');
  const [refusalFallbackEnabled, setRefusalFallbackEnabled] = useState(false);
  const [saveTierStatus, setSaveTierStatus] = useState('idle');
  const streamRef = useRef(null);
  const ttsAudioRef = useRef(null);
  /** Mirrors assistant reply text during SSE tokens — do not read from setState updaters for TTS (Strict Mode runs them twice). */
  const streamAssistantBufferRef = useRef('');
  const ttsFetchAbortRef = useRef(null);
  /** Prevents duplicate auto-read if `done` fires twice or updater replays. */
  const ttsAutoReadForAssistantRef = useRef(null);

  useEffect(() => {
    fetch(`${API}/models/tiers`)
      .then((r) => r.json())
      .then((data) => {
        const tm = data.tier_models || {};
        setTierModels({
          1: String(tm['1'] ?? tm[1] ?? ''),
          2: String(tm['2'] ?? tm[2] ?? ''),
          3: String(tm['3'] ?? tm[3] ?? ''),
        });
        setOllamaModels(Array.isArray(data.ollama_models) ? data.ollama_models : []);
        setFallbackModel(String(data.fallback_model ?? '').trim());
        setRefusalFallbackEnabled(!!data.refusal_fallback_enabled);
      })
      .catch(() => {});
  }, []);

  // Health polling
  useEffect(() => {
    const poll = async () => {
      try { const r = await fetch(`${API}/health`); if (r.ok) setHealth(await r.json()); }
      catch { setHealth(null); }
    };
    poll();
    const iv = setInterval(poll, 8000);
    return () => clearInterval(iv);
  }, []);

  // Sessions
  useEffect(() => {
    fetch(`${API}/sessions`).then(r => r.json()).then(setSessions).catch(() => {});
  }, []);

  const newChat = useCallback(() => {
    if (streamRef.current) streamRef.current.cancel();
    setCurrentSession(crypto.randomUUID());
    setMessages([]);
  }, []);

  const loadSession = useCallback(async (id) => {
    if (isStreaming) return;
    setCurrentSession(id);
    setMessages([]);
    try {
      const r = await fetch(`${API}/sessions/${id}/messages`);
      if (!r.ok) return;
      const stored = await r.json();
      setMessages(stored.map((m, idx) => ({
        id: idx, role: m.role, content: m.content,
        state: 'done', think: [], verification: [],
        announcement: null, webSearched: false, searchQueries: [], searchCount: 0,
        searchingText: null, feedback: null, modelUsed: null,
      })));
    } catch (e) { console.error('Load session failed:', e); }
  }, [isStreaming]);

  const deleteSession = useCallback(async (id, e) => {
    e.stopPropagation();
    try {
      await fetch(`${API}/sessions/${id}`, { method: 'DELETE' });
      setSessions(prev => prev.filter(s => s.id !== id));
      if (currentSession === id) { setCurrentSession(null); setMessages([]); }
    } catch {}
  }, [currentSession]);

  const clearHistory = useCallback(async () => {
    if (!window.confirm('Clear ALL chat history? This cannot be undone.')) return;
    try {
      await fetch(`${API}/sessions`, { method: 'DELETE' });
      setSessions([]); setMessages([]); setCurrentSession(null);
    } catch {}
  }, []);

  const stopStreaming = useCallback(() => {
    if (streamRef.current) streamRef.current.cancel();
    setIsStreaming(false);
  }, []);

  const speakText = useCallback(async (rawText) => {
    const text = plainForTts(rawText);
    if (!text || text.length < 2) return;
    let voice = 'en-GB-ThomasNeural';
    try {
      voice = localStorage.getItem('jar_edge_voice') || voice;
    } catch { /* ignore */ }
    try {
      ttsFetchAbortRef.current?.abort();
    } catch { /* ignore */ }
    const ac = new AbortController();
    ttsFetchAbortRef.current = ac;

    const prev = ttsAudioRef.current;
    if (prev) {
      try {
        prev.pause();
        prev.src = '';
      } catch { /* ignore */ }
      ttsAudioRef.current = null;
    }
    try {
      const r = await fetch(`${API}/voice/edge/speak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice }),
        signal: ac.signal,
      });
      if (ac.signal.aborted) return;
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        console.warn('Edge TTS failed', r.status, err);
        return;
      }
      const buf = await r.arrayBuffer();
      if (ac.signal.aborted) return;
      const blob = new Blob([buf], { type: 'audio/mpeg' });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      ttsAudioRef.current = audio;
      audio.onended = () => {
        URL.revokeObjectURL(url);
        if (ttsAudioRef.current === audio) ttsAudioRef.current = null;
      };
      await audio.play();
    } catch (e) {
      if (e?.name === 'AbortError') return;
      console.warn('Edge TTS playback failed', e);
    }
  }, []);

  const onTierModelsDraftChange = useCallback((tier, value) => {
    setTierModels((prev) => ({ ...prev, [tier]: value }));
  }, []);

  const saveTierModelsToServer = useCallback(async () => {
    setSaveTierStatus('saving');
    try {
      const r = await fetch(`${API}/models/tiers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tier_models: {
            1: tierModels[1]?.trim(),
            2: tierModels[2]?.trim(),
            3: tierModels[3]?.trim(),
          },
          fallback_model: fallbackModel.trim(),
          refusal_fallback_enabled: refusalFallbackEnabled,
        }),
      });
      if (!r.ok) {
        setSaveTierStatus('error');
        return;
      }
      const data = await r.json();
      const tm = data.tier_models || {};
      setTierModels({
        1: String(tm['1'] ?? ''),
        2: String(tm['2'] ?? ''),
        3: String(tm['3'] ?? ''),
      });
      setFallbackModel(String(data.fallback_model ?? '').trim());
      setRefusalFallbackEnabled(!!data.refusal_fallback_enabled);
      setSaveTierStatus('idle');
      try {
        const hr = await fetch(`${API}/health`);
        if (hr.ok) setHealth(await hr.json());
      } catch { /* ignore */ }
      try {
        const tr = await fetch(`${API}/models/tiers`);
        if (tr.ok) {
          const td = await tr.json();
          setOllamaModels(Array.isArray(td.ollama_models) ? td.ollama_models : []);
          setFallbackModel(String(td.fallback_model ?? '').trim());
          setRefusalFallbackEnabled(!!td.refusal_fallback_enabled);
        }
      } catch { /* ignore */ }
    } catch {
      setSaveTierStatus('error');
    }
  }, [tierModels, fallbackModel, refusalFallbackEnabled]);

  const sendFeedback = useCallback(async (msgId, query, response, rating) => {
    setMessages(prev => prev.map(m => m.id === msgId ? { ...m, feedback: rating } : m));
    try {
      await fetch(`${API}/feedback`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, response, rating }),
      });
    } catch {}
  }, []);

  const sendMessage = useCallback(async (query) => {
    if (!query.trim() || isStreaming) return;
    const sessionId = currentSession || crypto.randomUUID();
    if (!currentSession) setCurrentSession(sessionId);

    const userMsg = { role: 'user', content: query, id: Date.now() };
    const assistantId = Date.now() + 1;
    streamAssistantBufferRef.current = '';
    ttsAutoReadForAssistantRef.current = null;
    setMessages(prev => [...prev, userMsg, {
      role: 'assistant', content: '', think: [], id: assistantId,
      state: 'thinking', announcement: null, verification: [],
      modelUsed: null, webSearched: false, searchQueries: [], searchCount: 0,
      searchingText: null, feedback: null,
    }]);
    setIsStreaming(true);

    try {
      const response = await fetch(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, session_id: sessionId }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      streamRef.current = reader;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            switch (data.type) {
              case 'state':
                setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, state: data.state } : m));
                break;
              case 'meta': {
                const t = typeof data.tier === 'number' ? data.tier : parseInt(data.tier, 10);
                const lbl = TIER_LABELS[Number.isFinite(t) ? t : 0];
                setMessages(prev => prev.map(m => m.id === assistantId ? {
                  ...m,
                  power: Number.isFinite(t) ? t : m.power,
                  powerLabel: lbl || m.powerLabel,
                  modelUsed: data.model || m.modelUsed,
                } : m));
                break;
              }
              case 'tools': {
                setMessages((prev) => prev.map((m) => (m.id === assistantId ? {
                  ...m,
                  searchingText: data.searching_text !== undefined ? data.searching_text : m.searchingText,
                  webSearched: data.web_searched ?? m.webSearched,
                  searchQueries: Array.isArray(data.search_queries) ? data.search_queries : m.searchQueries,
                  searchCount: typeof data.search_count === 'number' ? data.search_count : m.searchCount,
                } : m)));
                break;
              }
              case 'token': {
                const piece = data.token ?? '';
                if (typeof piece === 'string' && piece.length) streamAssistantBufferRef.current += piece;
                setMessages(prev => prev.map(m => m.id === assistantId
                  ? { ...m, content: m.content + piece, state: 'responding' } : m));
                break;
              }
              case 'done': {
                const tierNum = typeof data.tier === 'number' ? data.tier : parseInt(data.tier, 10);
                const buffered = streamAssistantBufferRef.current;
                streamAssistantBufferRef.current = '';
                setMessages((prev) => prev.map((m) => (m.id === assistantId ? {
                  ...m,
                  state: 'done',
                  modelUsed: data.model_used ?? m.modelUsed,
                  power: Number.isFinite(tierNum) ? tierNum : m.power,
                  powerLabel: TIER_LABELS[tierNum] || m.powerLabel,
                } : m)));
                let auto = false;
                try {
                  auto = localStorage.getItem('jar_edge_autoread') === '1';
                } catch { /* ignore */ }
                if (
                  auto
                  && buffered.length > 2
                  && ttsAutoReadForAssistantRef.current !== assistantId
                ) {
                  ttsAutoReadForAssistantRef.current = assistantId;
                  queueMicrotask(() => speakText(buffered));
                }
                fetch(`${API}/sessions`).then(r => r.json()).then(setSessions).catch(() => {});
                break;
              }
            }
          } catch {}
        }
      }
    } catch (err) {
      streamAssistantBufferRef.current = '';
      setMessages(prev => prev.map(m => m.id === assistantId
        ? { ...m, content: `*Connection error — is Ollama running? (${err.message})*`, state: 'done' } : m));
    } finally {
      streamAssistantBufferRef.current = '';
      setIsStreaming(false);
    }
  }, [currentSession, isStreaming, speakText]);

  const online = health?.ollama;

  const voiceInputMode = useMemo(() => {
    if (typeof window === 'undefined') return 'off';
    if (health?.stt === true) return 'whisper';
    if (window.SpeechRecognition || window.webkitSpeechRecognition) return 'browser';
    return 'off';
  }, [health?.stt]);

  return (
    <div className="app">
      <Sidebar
        isOpen={sidebarOpen}
        sessions={sessions}
        currentSession={currentSession}
        onNewChat={newChat}
        onSessionClick={loadSession}
        onDeleteSession={deleteSession}
        onClearHistory={clearHistory}
        health={health}
      />

      <div className="main">
        {/* Topbar */}
        <div className="topbar">
          <button className="menu-btn" onClick={() => setSidebarOpen(o => !o)} id="sidebar-toggle" title="Toggle sidebar">
            <Menu size={18} />
          </button>

          <div className="topbar-spacer" />

          <ModelSelector
            tierModels={tierModels}
            onTierModelsDraftChange={onTierModelsDraftChange}
            ollamaModels={ollamaModels}
            onSave={saveTierModelsToServer}
            saveStatus={saveTierStatus}
            fallbackModel={fallbackModel}
            onFallbackModelChange={setFallbackModel}
            refusalFallbackEnabled={refusalFallbackEnabled}
            onRefusalFallbackEnabledChange={setRefusalFallbackEnabled}
          />

          <VoiceSelector edgeTtsOk={health?.edge_tts === true} />

          {health && (
            <div className="health-chip" id="health-chip" title="Ollama · tier 2 (standard) default tag">
              {online ? <Wifi size={12} style={{ color: 'var(--gem-green)' }} /> : <WifiOff size={12} style={{ color: 'var(--gem-red)' }} />}
              <span style={{ color: online ? 'var(--gem-green)' : 'var(--gem-red)' }}>
                {online
                  ? (health.tier_models?.['2']?.split(':')[0] || health.model?.split(':')[0] || 'Online')
                  : 'Offline'}
              </span>
            </div>
          )}
        </div>

        {/* Chat */}
        <ChatWindow
          messages={messages}
          isStreaming={isStreaming}
          onSendQuick={sendMessage}
          onFeedback={sendFeedback}
          onSpeak={health?.edge_tts === true ? speakText : undefined}
        />

        {/* Input */}
        <InputBar
          onSend={sendMessage}
          isStreaming={isStreaming}
          onStop={stopStreaming}
          voiceInputMode={voiceInputMode}
        />
      </div>
    </div>
  );
}
