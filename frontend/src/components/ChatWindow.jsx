import React, { useRef, useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ChevronDown, Brain, ShieldCheck, Globe, Cpu,
  AlertTriangle, Zap, ThumbsUp, ThumbsDown, Search, Volume2,
} from 'lucide-react';

const QUICK = [
  { title: 'System status', sub: 'Hardware & reasoning tiers overview', prompt: 'Run a complete system status report. Hardware thermals, memory, and all reasoning tiers.' },
  { title: 'Code review', sub: 'Analyze and debug code', prompt: 'I need you to review and debug some code for me.' },
  { title: 'Deep recall', sub: 'Search your memory banks', prompt: 'What have we worked on recently? Pull relevant context from your episodic memory banks.' },
  { title: 'Web research', sub: 'Multi-hop agentic search', prompt: 'Research and compare the latest AI model releases. Use your full web research capabilities.' },
];

function ThinkAccordion({ label, content, color = 'var(--gem-amber)', contentClass = 'think-content', icon }) {
  const [open, setOpen] = useState(false);
  if (!content) return null;
  const lines = Array.isArray(content) ? content : [content];
  return (
    <div className="think-block">
      <button className="think-toggle" onClick={() => setOpen(o => !o)} style={{ color }}>
        <span className={`think-chevron ${open ? 'open' : ''}`}><ChevronDown size={13} /></span>
        {icon}
        {label}
      </button>
      {open && (
        <div className={contentClass}>
          {Array.isArray(content)
            ? content.map((s, i) => <div key={i} style={{ marginBottom: 4 }}><span style={{ opacity: 0.5 }}>{String(i + 1).padStart(2, '0')}. </span>{s}</div>)
            : <div style={{ whiteSpace: 'pre-wrap' }}>{content}</div>
          }
        </div>
      )}
    </div>
  );
}

function WebBadge({ count, queries }) {
  const [open, setOpen] = useState(false);
  if (!count) return null;
  return (
    <span className="web-badge" onClick={() => setOpen(o => !o)}>
      <Globe size={10} /> {count} sources {open ? '▲' : '▼'}
      {open && queries?.length > 0 && (
        <span className="search-popup">
          {queries.map((q, i) => <span key={i} className="search-query">→ {q}</span>)}
        </span>
      )}
    </span>
  );
}

function FeedbackRow({ msg, onFeedback, userQuery }) {
  if (!msg.content || msg.state !== 'done') return null;
  const voted = msg.feedback;
  return (
    <div className="feedback-row">
      <button
        className={`feedback-btn ${voted === 1 ? 'active-up' : ''}`}
        onClick={() => !voted && onFeedback(msg.id, userQuery, msg.content, 1)}
        disabled={!!voted} title="Helpful"
      ><ThumbsUp size={13} /></button>
      <button
        className={`feedback-btn ${voted === -1 ? 'active-down' : ''}`}
        onClick={() => !voted && onFeedback(msg.id, userQuery, msg.content, -1)}
        disabled={!!voted} title="Not helpful"
      ><ThumbsDown size={13} /></button>
      {voted && <span className="feedback-confirmed">{voted === 1 ? '✦ Reinforcing.' : '✦ Noted.'}</span>}
    </div>
  );
}

export default function ChatWindow({ messages, isStreaming, onSendQuick, onFeedback, onSpeak }) {
  const bottomRef = useRef(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="chat-window">
        <div className="chat-inner" style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <div className="welcome">
            <div className="welcome-gem">✦</div>
            <h1>Hello, Sir.</h1>
            <p className="welcome-sub">J.A.R. is online — adaptive power scaling, memory, and web research active.</p>
            <div className="quick-grid">
              {QUICK.map(q => (
                <button key={q.title} className="quick-card" onClick={() => onSendQuick(q.prompt)} id={`quick-${q.title.replace(/\s+/g, '-').toLowerCase()}`}>
                  <span className="quick-card-title">{q.title}</span>
                  <span className="quick-card-sub">{q.sub}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-window" id="chat-window">
      <div className="chat-inner">
        {messages.map((msg, idx) => {
          const prevUser = messages[idx - 1];
          return (
            <div key={msg.id} className={`message ${msg.role}`}>

              {msg.role === 'user' && (
                <div className="user-bubble">
                  {msg.content}
                  {msg.images?.length > 0 && (
                    <div className="message-images">
                      {msg.images.map((img, i) => (
                        <img key={i} src={`data:image/jpeg;base64,${img}`} alt="Attached" className="message-img"
                          onClick={() => window.open(`data:image/jpeg;base64,${img}`, '_blank')} />
                      ))}
                    </div>
                  )}
                </div>
              )}

              {msg.role === 'assistant' && (
                <div className="assistant-row">
                  <div className="gem-avatar">✦</div>
                  <div className="assistant-body">

                    {/* Meta chips */}
                    <div className="msg-meta">
                      <span className="msg-name">JAR</span>
                      {msg.powerLabel && (
                        <span className="chip chip-blue" style={{ background: `${msg.powerColor}18`, borderColor: `${msg.powerColor}30`, color: msg.powerColor }}>
                          {['', '⚡', '🧠', '🔬'][msg.power]} {msg.powerLabel}
                        </span>
                      )}
                      {msg.webSearched && <WebBadge count={msg.searchCount} queries={msg.searchQueries} />}
                      {msg.modelUsed && (
                        <span className="chip chip-blue" style={{ fontSize: 10 }}>
                          <Cpu size={9} /> {msg.modelUsed.split(':')[0]}
                        </span>
                      )}
                    </div>

                    {/* System announcement */}
                    {msg.announcement && (
                      <div className="system-announcement">
                        <Zap size={14} style={{ flexShrink: 0, color: 'var(--gem-blue)' }} />
                        {msg.announcement}
                      </div>
                    )}

                    {/* SAT upgrade */}
                    {msg.satUpgraded && (
                      <div className="sat-notice"><Zap size={11} />{msg.satText}</div>
                    )}

                    {/* Pushback */}
                    {msg.pushback && (
                      <div className="pushback-block" style={{
                        borderColor: msg.gvuOpinion === 'oppose' ? 'rgba(242,139,130,0.35)' : 'rgba(253,214,99,0.35)',
                        background: msg.gvuOpinion === 'oppose' ? 'rgba(242,139,130,0.07)' : 'rgba(253,214,99,0.07)',
                      }}>
                        <div className="pushback-header">
                          <AlertTriangle size={13} color={msg.gvuOpinion === 'oppose' ? 'var(--gem-red)' : 'var(--gem-amber)'} />
                          <span style={{ color: msg.gvuOpinion === 'oppose' ? 'var(--gem-red)' : 'var(--gem-amber)' }}>
                            {msg.gvuOpinion === 'oppose' ? 'JAR OPPOSES' : 'JAR ADVISES CAUTION'}
                          </span>
                        </div>
                        <p className="pushback-text">{msg.pushback}</p>
                      </div>
                    )}

                    {/* Searching chip */}
                    {msg.searchingText && !msg.webSearched && (
                      <div className="searching-chip">
                        <span className="searching-dot" />
                        <Search size={12} /> {msg.searchingText}
                      </div>
                    )}

                    {/* Thought (internal monologue) */}
                    <ThinkAccordion
                      label="Internal monologue"
                      content={msg.thought}
                      color="var(--gem-purple)"
                      contentClass="thought-content"
                    />

                    {/* Think steps (CoD) */}
                    {msg.think?.length > 0 && (
                      <ThinkAccordion
                        label={`Thought process (${msg.think.length} steps)`}
                        content={msg.think}
                        color="var(--gem-amber)"
                        contentClass="think-content"
                        icon={<Brain size={12} style={{ marginRight: 3 }} />}
                      />
                    )}

                    {/* Thinking spinner */}
                    {!msg.content && msg.state === 'thinking' && (
                      <div className="thinking-dots">
                        <div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" />
                      </div>
                    )}

                    {/* Responding dots */}
                    {!msg.content && msg.state === 'responding' && (
                      <div className="thinking-dots">
                        <div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" />
                      </div>
                    )}

                    {/* Main content */}
                    {msg.content && (
                      <div className="prose">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.content
                            .replace(/<thought>[\s\S]*?<\/thought>/gi, '')
                            .replace(/<think>[\s\S]*?<\/think>/gi, '')
                            .trim()}
                        </ReactMarkdown>
                      </div>
                    )}

                    {/* CoVe verification */}
                    {msg.state === 'done' && msg.verification?.length > 0 && (
                      <ThinkAccordion
                        label={`Verification (${msg.verification.length} checks)`}
                        content={msg.verification}
                        color="var(--gem-green)"
                        contentClass="cove-content"
                        icon={<ShieldCheck size={12} style={{ marginRight: 3 }} />}
                      />
                    )}

                    {/* Edge TTS */}
                    {onSpeak && msg.content && msg.state === 'done' && (
                      <div className="tts-row">
                        <button
                          type="button"
                          className="feedback-btn"
                          title="Speak with Edge TTS"
                          onClick={() => onSpeak(msg.content)}
                          id={`speak-${msg.id}`}
                        >
                          <Volume2 size={13} />
                        </button>
                      </div>
                    )}

                    {/* Feedback */}
                    {onFeedback && (
                      <FeedbackRow
                        msg={msg}
                        onFeedback={onFeedback}
                        userQuery={prevUser?.content || ''}
                      />
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
