import React, { useState, useEffect, useRef, useMemo } from 'react';
import { ChevronDown, Cpu, Save } from 'lucide-react';

const TIER_META = [
  { tier: 1, label: 'Express', sub: 'Auto: short / light' },
  { tier: 2, label: 'Standard', sub: 'Auto: default' },
  { tier: 3, label: 'Deep', sub: 'Auto: long or complex' },
];

function sortedModels(ollamaModels) {
  if (!Array.isArray(ollamaModels)) return [];
  return [...ollamaModels].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
}

function tierSelectOptions(tier, tierModels, ollamaModels) {
  const models = sortedModels(ollamaModels);
  const cur = String(tierModels[tier] ?? '').trim();
  const options = [];

  if (cur && !models.includes(cur)) {
    options.push({
      value: cur,
      label: `${cur} (not in current Ollama list)`,
      key: `orphan-${tier}-${cur}`,
    });
  }
  for (const name of models) {
    options.push({ value: name, label: name, key: name });
  }
  return { options, current: cur, hasModels: models.length > 0 };
}

export default function ModelSelector({
  tierModels,
  onTierModelsDraftChange,
  ollamaModels,
  onSave,
  saveStatus,
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  const modelCount = useMemo(
    () => (Array.isArray(ollamaModels) ? ollamaModels.length : 0),
    [ollamaModels],
  );

  useEffect(() => {
    const onDoc = (e) => {
      if (!wrapRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener('click', onDoc);
    return () => document.removeEventListener('click', onDoc);
  }, []);

  return (
    <div className="model-selector-wrap" ref={wrapRef}>
      <button
        type="button"
        className="model-selector-btn"
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        title="Choose which downloaded Ollama model backs each auto tier"
        id="model-config-btn"
      >
        <Cpu size={15} />
        <span className="model-selector-btn-text">Models</span>
        <ChevronDown size={14} className={open ? 'chev-open' : ''} />
      </button>

      {open && (
        <div className="model-dropdown model-dropdown-wide" onClick={(e) => e.stopPropagation()}>
          <div className="model-dropdown-title">Ollama models per tier</div>
          <p className="tier-model-lede">
            Each dropdown lists tags from your machine (
            <strong>{modelCount}</strong>
            {' '}
            {modelCount === 1 ? 'model' : 'models'}
            ). Pick one per tier, then save.
          </p>
          {TIER_META.map(({ tier, label, sub }) => {
            const { options, current, hasModels } = tierSelectOptions(tier, tierModels, ollamaModels);
            const showPlaceholder = hasModels && !current;
            return (
              <label key={tier} className="tier-model-field">
                <span className="tier-model-label">
                  Tier {tier} — {label}
                  <small>{sub}</small>
                </span>
                <select
                  className="tier-model-input tier-model-select"
                  value={current}
                  onChange={(e) => onTierModelsDraftChange(tier, e.target.value)}
                  disabled={!hasModels && !current}
                  id={`tier-model-select-${tier}`}
                >
                  {showPlaceholder && (
                    <option value="" disabled>
                      — Select a model —
                    </option>
                  )}
                  {!hasModels && !current && (
                    <option value="">
                      No models — start Ollama and pull a model
                    </option>
                  )}
                  {options.map(({ value, label: optLabel, key }) => (
                    <option key={key} value={value}>
                      {optLabel}
                    </option>
                  ))}
                </select>
              </label>
            );
          })}
          <button
            type="button"
            className="tier-model-save"
            onClick={() => onSave()}
            disabled={saveStatus === 'saving'}
            id="tier-model-save-btn"
          >
            <Save size={14} />
            {saveStatus === 'saving' ? 'Saving…' : saveStatus === 'error' ? 'Retry save' : 'Save to disk'}
          </button>
          {saveStatus === 'error' && (
            <p className="tier-model-save-err">Save failed — check backend logs.</p>
          )}
          <p className="tier-model-hint">Writes <code>jar_tier_models.json</code> in the project root (overrides .env for tiers).</p>
        </div>
      )}
    </div>
  );
}
