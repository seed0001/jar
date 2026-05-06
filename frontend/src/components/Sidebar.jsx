import React, { useState } from 'react';
import { Plus, MessageSquare, Trash2, WifiOff, Wifi, PenSquare } from 'lucide-react';

export default function Sidebar({ isOpen, sessions, currentSession, onNewChat, onSessionClick, onDeleteSession, onClearHistory, health }) {
  const online = health?.ollama;

  const fmt = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 86400) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (diff < 604800) return d.toLocaleDateString([], { weekday: 'short' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  return (
    <div className={`sidebar ${isOpen ? '' : 'collapsed'}`}>
      {/* Header */}
      <div className="sidebar-header">
        <div className="gem-logo">✦</div>
        <span className="sidebar-title">J.A.R.</span>
      </div>

      {/* New chat button */}
      <button className="new-chat-btn" onClick={onNewChat} id="new-chat-btn">
        <PenSquare size={15} />
        New chat
      </button>

      {/* Sessions */}
      {sessions.length > 0 && (
        <>
          <div className="sessions-label">Recent</div>
          <div className="sessions-list">
            {sessions.map(s => (
              <div
                key={s.id}
                className={`session-item ${s.id === currentSession ? 'active' : ''}`}
                onClick={() => onSessionClick(s.id)}
                id={`session-${s.id}`}
              >
                <MessageSquare size={13} style={{ color: 'var(--gem-text-faint)', flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="session-title">{s.title || 'Untitled chat'}</div>
                  <div className="session-date">{fmt(s.updated_at || s.created_at)}</div>
                </div>
                <button
                  className="session-delete-btn"
                  onClick={(e) => onDeleteSession(s.id, e)}
                  title="Delete chat"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {sessions.length === 0 && (
        <div style={{ padding: '20px 16px', color: 'var(--gem-text-faint)', fontSize: 13 }}>
          No recent chats
        </div>
      )}

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="status-badge">
          <div className={`status-dot ${online ? '' : 'offline'}`} />
          <span style={{ flex: 1 }}>
            {online ? (health?.model?.split(':')[0] || 'Ollama') : 'Ollama offline'}
          </span>
          {online ? <Wifi size={12} /> : <WifiOff size={12} />}
        </div>
        {sessions.length > 0 && (
          <button className="clear-history-btn" onClick={onClearHistory}>
            <Trash2 size={12} /> Clear all history
          </button>
        )}
      </div>
    </div>
  );
}
