import React, { useState, useEffect, useMemo, useRef } from 'react';
import { ChevronDown, Mic, Volume2 } from 'lucide-react';

const STORAGE_VOICE = 'jar_edge_voice';
const STORAGE_AUTOREAD = 'jar_edge_autoread';

export default function VoiceSelector({ edgeTtsOk }) {
  const [open, setOpen] = useState(false);
  const [voices, setVoices] = useState([]);
  const [defaultVoice, setDefaultVoice] = useState('en-GB-ThomasNeural');
  const [voiceId, setVoiceId] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_VOICE) || '';
    } catch {
      return '';
    }
  });
  const [autoRead, setAutoRead] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_AUTOREAD) === '1';
    } catch {
      return false;
    }
  });
  const [search, setSearch] = useState('');
  const wrapRef = useRef(null);

  useEffect(() => {
    const onDoc = (e) => {
      if (!wrapRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener('click', onDoc);
    return () => document.removeEventListener('click', onDoc);
  }, []);

  useEffect(() => {
    if (!edgeTtsOk) return;
    fetch('/voice/edge/voices')
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data.voices)) setVoices(data.voices);
        if (data.default_voice) setDefaultVoice(data.default_voice);
      })
      .catch(() => {});
  }, [edgeTtsOk]);

  useEffect(() => {
    if (!voiceId && defaultVoice) setVoiceId(defaultVoice);
  }, [defaultVoice, voiceId]);

  useEffect(() => {
    if (!voices.length || !voiceId) return;
    if (voices.some((v) => v.id === voiceId)) return;
    const next =
      defaultVoice && voices.some((v) => v.id === defaultVoice)
        ? defaultVoice
        : voices[0].id;
    setVoiceId(next);
    try {
      localStorage.setItem(STORAGE_VOICE, next);
    } catch { /* ignore */ }
  }, [voices, voiceId, defaultVoice]);

  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    if (!s) return voices.slice(0, 120);
    return voices
      .filter(
        (v) =>
          (v.id || '').toLowerCase().includes(s) ||
          (v.name || '').toLowerCase().includes(s) ||
          (v.locale || '').toLowerCase().includes(s),
      )
      .slice(0, 150);
  }, [voices, search]);

  const label = useMemo(() => {
    const v = voices.find((x) => x.id === voiceId);
    if (v) return `${v.locale?.split('-')[0] || ''} · ${v.name?.slice(0, 22) || v.id}`;
    return voiceId?.split('-').pop()?.replace('Neural', '') || 'Voice';
  }, [voices, voiceId]);

  const persistVoice = (id) => {
    setVoiceId(id);
    try {
      localStorage.setItem(STORAGE_VOICE, id);
    } catch { /* ignore */ }
  };

  const persistAuto = (on) => {
    setAutoRead(on);
    try {
      localStorage.setItem(STORAGE_AUTOREAD, on ? '1' : '0');
    } catch { /* ignore */ }
  };

  if (!edgeTtsOk) {
    return (
      <div className="voice-selector-wrap voice-selector-off" title="Install edge-tts and restart backend">
        <Mic size={14} style={{ opacity: 0.35 }} />
        <span className="voice-selector-off-text">TTS off</span>
      </div>
    );
  }

  return (
    <div className="voice-selector-wrap" ref={wrapRef}>
      <button
        type="button"
        className="model-selector-btn voice-selector-btn"
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        title="Microsoft Edge neural TTS — pick a voice"
        id="voice-config-btn"
      >
        <Volume2 size={15} />
        <span className="model-selector-btn-text">{label}</span>
        <ChevronDown size={14} className={open ? 'chev-open' : ''} />
      </button>

      {open && (
        <div className="model-dropdown model-dropdown-wide voice-dropdown" onClick={(e) => e.stopPropagation()}>
          <div className="model-dropdown-title">Edge TTS · neural voices</div>
          <p className="tier-model-lede">Requires internet (Microsoft Edge TTS). Text is sent to Microsoft for synthesis.</p>

          <label className="voice-autoread">
            <input
              type="checkbox"
              checked={autoRead}
              onChange={(e) => persistAuto(e.target.checked)}
            />
            Read assistant replies aloud when they finish
          </label>

          <input
            type="search"
            className="tier-model-input voice-search"
            placeholder="Search locale, name, or voice id…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          <label className="tier-model-field">
            <span className="tier-model-label">Voice</span>
            <select
              className="tier-model-input voice-select"
              value={voiceId}
              onChange={(e) => persistVoice(e.target.value)}
              size={Math.min(10, Math.max(4, filtered.length))}
            >
              {filtered.length === 0 && <option value={voiceId}>{voiceId || 'Loading…'}</option>}
              {filtered.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.locale} — {v.name || v.id}
                </option>
              ))}
            </select>
          </label>
          <p className="tier-model-hint">Showing up to {filtered.length} matches. Narrow with search for more.</p>
        </div>
      )}
    </div>
  );
}
