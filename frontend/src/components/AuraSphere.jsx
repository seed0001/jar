import React, { useEffect, useRef, useCallback } from 'react';

const NUM_BARS = 48;
const FFT_SIZE = 128;

/**
 * AuraSphere v3 — Audio-Reactive + Tier-adaptive animated presence.
 *
 * Visuals:
 *   - idle:      Slow-pulsing blue circle
 *   - listening: Expanding red pulse (mic active)
 *   - thinking:  Rotating crystalline lattice (amber)
 *   - responding: Streaming cyan bars
 *   - speaking:  FFT-reactive bars that pulse with TTS audio volume
 *   - skill:     Purple glow during Skill Injection
 *   - searching: Green agentic glow
 *
 * Power tiers:
 *   1 → circle, 2 → hexagon, 3 → dodecagon with inner lattice
 */
export default function AuraSphere({ state = 'idle', powerLevel = 2, audioStream = null }) {
  const canvasRef  = useRef(null);
  const animRef    = useRef(null);
  const phaseRef   = useRef(0);
  const analyserRef = useRef(null);
  const fftDataRef  = useRef(new Uint8Array(FFT_SIZE / 2));

  // ── Audio FFT setup ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!audioStream) {
      analyserRef.current = null;
      fftDataRef.current = new Uint8Array(FFT_SIZE / 2);
      return;
    }
    try {
      const audioCtx  = new (window.AudioContext || window.webkitAudioContext)();
      const source    = audioCtx.createMediaStreamSource(audioStream);
      const analyser  = audioCtx.createAnalyser();
      analyser.fftSize = FFT_SIZE;
      analyser.smoothingTimeConstant = 0.82;
      source.connect(analyser);
      analyserRef.current = analyser;
      fftDataRef.current  = new Uint8Array(analyser.frequencyBinCount);
      return () => { audioCtx.close(); analyserRef.current = null; };
    } catch (e) {
      console.warn('AudioContext unavailable for Aura FFT:', e);
    }
  }, [audioStream]);

  const STATE_COLORS = {
    idle:       { c1: '#00D4FF', c2: '#0066CC', alpha: 0.25 },
    listening:  { c1: '#EF4444', c2: '#FF6666', alpha: 0.80 },
    thinking:   { c1: '#F59E0B', c2: '#FF8800', alpha: 0.70 },
    responding: { c1: '#00D4FF', c2: '#00FFAA', alpha: 0.85 },
    speaking:   { c1: '#00D4FF', c2: '#00FF88', alpha: 1.00 },
    skill:      { c1: '#8B5CF6', c2: '#A855F7', alpha: 0.90 },
    searching:  { c1: '#10B981', c2: '#34D399', alpha: 0.85 },
  };

  const TIER_CONFIG = {
    1: { sides: 0,   rotSpeed: 0.005, ringCount: 2, coreR: 10 },
    2: { sides: 6,   rotSpeed: 0.012, ringCount: 3, coreR: 13 },
    3: { sides: 12,  rotSpeed: 0.028, ringCount: 4, coreR: 15 },
  };

  const STATE_SPEED = {
    idle: 0.6, listening: 1.4, thinking: 1.8, responding: 2.2, speaking: 3.0,
    skill: 2.8, searching: 1.6,
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width  = 200;
    const H = canvas.height = 200;
    const cx = W / 2, cy = H / 2;

    const tier   = TIER_CONFIG[powerLevel] || TIER_CONFIG[2];
    const colors = STATE_COLORS[state] || STATE_COLORS.idle;
    const speedMult = STATE_SPEED[state] || 1;
    const rotSpeed  = tier.rotSpeed * speedMult;

    const animate = () => {
      phaseRef.current += rotSpeed;
      const phase = phaseRef.current;

      // Sample FFT data if analyser is connected
      let fftAvg = 0;
      if (analyserRef.current) {
        analyserRef.current.getByteFrequencyData(fftDataRef.current);
        const sum = fftDataRef.current.reduce((a, b) => a + b, 0);
        fftAvg = sum / fftDataRef.current.length / 255; // 0..1
      }

      ctx.clearRect(0, 0, W, H);

      // ── Outer glow rings ────────────────────────────────────────────────────
      for (let r = 0; r < tier.ringCount; r++) {
        const fftPulse = state === 'speaking' ? fftAvg * 18 : 0;
        const ripple = state === 'speaking'
          ? Math.sin(phase * 4 + r) * 12 + fftPulse
          : state === 'listening'
          ? Math.sin(phase * 3 + r * 2) * 8
          : Math.sin(phase + r * 1.2) * 4;
        const radius = 65 + r * 12 + ripple;
        const a = (0.06 - r * 0.012) * colors.alpha;
        const hex = Math.max(0, Math.min(255, Math.round(a * 255))).toString(16).padStart(2, '0');
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.strokeStyle = colors.c1 + hex;
        ctx.lineWidth = state === 'speaking' ? 1.5 + fftAvg : 1;
        ctx.stroke();
      }

      // ── Geometric shape (power-tier adaptive) ───────────────────────────────
      if (tier.sides === 0) {
        const r2 = 42 + Math.sin(phase * 0.8) * 6;
        ctx.beginPath();
        ctx.arc(cx, cy, r2, 0, Math.PI * 2);
        const a = 0.3 * colors.alpha;
        ctx.strokeStyle = colors.c1 + Math.round(a * 255).toString(16).padStart(2, '0');
        ctx.lineWidth = 1.5;
        ctx.stroke();
      } else {
        const sides = tier.sides;
        const radius = 44 + Math.sin(phase * 0.5) * (powerLevel === 3 ? 8 : 5);
        ctx.beginPath();
        for (let i = 0; i <= sides; i++) {
          const angle = (i / sides) * Math.PI * 2 + phase;
          const wobble = Math.sin(phase * 1.5 + i * (Math.PI / sides)) * (powerLevel === 3 ? 8 : 4);
          const r3 = radius + wobble;
          const x  = cx + Math.cos(angle) * r3;
          const y  = cy + Math.sin(angle) * r3;
          i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        const polyAlpha = (state === 'thinking' ? 0.55 : 0.35) * colors.alpha;
        ctx.strokeStyle = colors.c1 + Math.round(polyAlpha * 255).toString(16).padStart(2, '0');
        ctx.lineWidth = powerLevel === 3 ? 2 : 1.5;
        ctx.stroke();

        // Inner inverted polygon (3/3 only)
        if (powerLevel === 3 && state !== 'idle') {
          const innerRadius = 26 + Math.sin(phase * 2) * 4;
          ctx.beginPath();
          for (let i = 0; i <= sides / 2; i++) {
            const angle = (i / (sides / 2)) * Math.PI * 2 - phase * 0.7;
            const x = cx + Math.cos(angle) * innerRadius;
            const y = cy + Math.sin(angle) * innerRadius;
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
          }
          ctx.strokeStyle = colors.c2 + '44';
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }

      // ── Audio-reactive bars ─────────────────────────────────────────────────
      if (['speaking', 'responding', 'listening'].includes(state)) {
        for (let i = 0; i < NUM_BARS; i++) {
          const angle   = (i / NUM_BARS) * Math.PI * 2;
          const barPhase = phase * (state === 'speaking' ? 3.5 : 2) + i * 0.25;

          // FFT-driven bar lengths when speaking
          let barLen;
          if (state === 'speaking' && analyserRef.current) {
            const fftIdx = Math.floor((i / NUM_BARS) * fftDataRef.current.length);
            const fftVal = (fftDataRef.current[fftIdx] || 0) / 255;
            barLen = 8 + fftVal * 36 * colors.alpha;
          } else {
            const maxBar = state === 'speaking' ? 28 : state === 'listening' ? 22 : 18;
            barLen = 8 + Math.abs(Math.sin(barPhase)) * maxBar * colors.alpha;
          }

          const innerR = 50;
          const x1 = cx + Math.cos(angle) * innerR;
          const y1 = cy + Math.sin(angle) * innerR;
          const x2 = cx + Math.cos(angle) * (innerR + barLen);
          const y2 = cy + Math.sin(angle) * (innerR + barLen);

          const g = ctx.createLinearGradient(x1, y1, x2, y2);
          g.addColorStop(0, colors.c1 + 'CC');
          g.addColorStop(1, colors.c2 + '22');
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.strokeStyle = g;
          ctx.lineWidth = state === 'speaking' ? 2.5 : 1.5;
          ctx.stroke();
        }
      }

      // ── Central core orb ────────────────────────────────────────────────────
      const fftCore = state === 'speaking' ? fftAvg * 6 : 0;
      const coreR = state === 'speaking'
        ? tier.coreR + Math.sin(phase * 4) * 5 + fftCore
        : state === 'thinking'
        ? tier.coreR + Math.sin(phase * 2) * 3
        : state === 'listening'
        ? tier.coreR + Math.sin(phase * 3) * 4
        : tier.coreR;

      const coreGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR + 4);
      coreGrad.addColorStop(0, colors.c1 + 'FF');
      coreGrad.addColorStop(0.6, colors.c1 + '66');
      coreGrad.addColorStop(1, 'transparent');
      ctx.beginPath();
      ctx.arc(cx, cy, coreR + 4, 0, Math.PI * 2);
      ctx.fillStyle = coreGrad;
      ctx.fill();

      // "J" label
      ctx.font = 'bold 14px Inter, sans-serif';
      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.globalAlpha = state === 'idle' ? 0.65 : 0.95;
      ctx.fillText('J', cx, cy);
      ctx.globalAlpha = 1;

      animRef.current = requestAnimationFrame(animate);
    };

    animRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animRef.current);
  }, [state, powerLevel, audioStream]);

  const LABELS = {
    idle:       'STANDBY',
    listening:  '● LISTENING',
    thinking:   '◈ PROCESSING',
    responding: '▶ GENERATING',
    speaking:   '♦ SPEAKING',
    skill:      '★ SKILL ACTIVE',
    searching:  '○ RESEARCHING',
  };

  const LABEL_COLORS = {
    idle: 'var(--text-2)', listening: 'var(--red)',
    thinking: 'var(--amber)', responding: 'var(--cyan)', speaking: 'var(--cyan)',
    skill: '#A78BFA', searching: 'var(--green)',
  };

  const TIER_LABELS = { 1: '1/3 · Express', 2: '2/3 · Standard', 3: '3/3 · Deep' };

  return (
    <div className="aura-container">
      <canvas ref={canvasRef} className="aura-canvas" />
      <div className="aura-label" style={{ color: LABEL_COLORS[state] }}>
        {LABELS[state]}
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-2)', fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.06em' }}>
        {TIER_LABELS[powerLevel]}
      </div>
    </div>
  );
}
