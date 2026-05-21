import React, { useState, useEffect } from 'react';

// ── Constants ─────────────────────────────────────────────────────────────────

const HALF_LIFE_HOURS = 5;
const LS_LOGS = 'dose_logs';
const LS_CUSTOM = 'dose_custom_drinks';

const PRESETS = [
  { name: 'Coffee',       mg: 95  },
  { name: 'Espresso',     mg: 64  },
  { name: 'Energy Drink', mg: 160 },
  { name: 'Tea',          mg: 47  },
  { name: 'Soda',         mg: 34  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function loadLS(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}

function calcActive(logs) {
  const now = Date.now();
  const cutoff = now - 24 * 3_600_000;
  return logs
    .filter(l => l.timestamp > cutoff)
    .reduce((sum, l) => {
      const hrs = (now - l.timestamp) / 3_600_000;
      return sum + l.caffeinemg * Math.pow(0.5, hrs / HALF_LIFE_HOURS);
    }, 0);
}

function isToday(ts) {
  return new Date(ts).toDateString() === new Date().toDateString();
}

function statusFor(mg) {
  if (mg < 200) return { color: '#22c55e', label: 'Safe',     ring: '#166534' };
  if (mg < 400) return { color: '#eab308', label: 'Moderate', ring: '#854d0e' };
  return         { color: '#ef4444', label: 'High',     ring: '#7f1d1d' };
}

function fmtTime(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function nowLocal() {
  const d = new Date();
  return new Date(d - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Card({ children, className = '' }) {
  return (
    <div className={`bg-gray-900 rounded-2xl border border-gray-800 p-5 ${className}`}>
      {children}
    </div>
  );
}

function SectionLabel({ children }) {
  return <p className="text-xs text-gray-500 uppercase tracking-widest mb-4">{children}</p>;
}

function Input({ className = '', ...props }) {
  return (
    <input
      style={{ colorScheme: 'dark' }}
      className={`w-full bg-gray-800 text-gray-100 text-sm rounded-xl px-3 py-2.5 outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-600 ${className}`}
      {...props}
    />
  );
}

// Circular gauge using SVG
function Gauge({ value, max = 400, color }) {
  const R = 28;
  const circ = 2 * Math.PI * R;
  const pct = Math.min(value / max, 1);
  return (
    <svg width="72" height="72" viewBox="0 0 72 72">
      <circle cx="36" cy="36" r={R} fill="none" stroke="#1f2937" strokeWidth="7" />
      <circle
        cx="36" cy="36" r={R}
        fill="none"
        stroke={color}
        strokeWidth="7"
        strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={circ * (1 - pct)}
        transform="rotate(-90 36 36)"
      />
      <text
        x="36" y="40"
        textAnchor="middle"
        fill="#d1d5db"
        fontSize="11"
        fontWeight="600"
      >
        {Math.round(pct * 100)}%
      </text>
    </svg>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function Dose() {
  const [logs,    setLogs]    = useState(() => loadLS(LS_LOGS,   []));
  const [customs, setCustoms] = useState(() => loadLS(LS_CUSTOM, []));
  const [tab,     setTab]     = useState('today');
  const [active,  setActive]  = useState(0);

  // Log form state
  const [showLog,     setShowLog]     = useState(false);
  const [selDrink,    setSelDrink]    = useState('Coffee');
  const [mgInput,     setMgInput]     = useState(95);
  const [tsInput,     setTsInput]     = useState('');
  const [customName,  setCustomName]  = useState('');

  // Custom drink form state
  const [showAddCustom, setShowAddCustom] = useState(false);
  const [newName,       setNewName]       = useState('');
  const [newMgInput,    setNewMgInput]    = useState('');

  // Persist to localStorage
  useEffect(() => { localStorage.setItem(LS_LOGS,   JSON.stringify(logs));    }, [logs]);
  useEffect(() => { localStorage.setItem(LS_CUSTOM, JSON.stringify(customs)); }, [customs]);

  // Recalculate active caffeine every 30 s
  useEffect(() => {
    const calc = () => setActive(calcActive(logs));
    calc();
    const id = setInterval(calc, 30_000);
    return () => clearInterval(id);
  }, [logs]);

  // All selectable drinks (presets + saved customs)
  const allDrinks = [
    ...PRESETS,
    ...customs.map(c => ({ name: c.name, mg: c.defaultMg })),
  ];

  // ── Log form handlers ────────────────────────────────────────────────────

  function openLogForm() {
    setSelDrink('Coffee');
    setMgInput(95);
    setTsInput(nowLocal());
    setCustomName('');
    setShowLog(true);
  }

  function pickDrink(name) {
    setSelDrink(name);
    if (name !== 'Custom') {
      const d = allDrinks.find(d => d.name === name);
      if (d) setMgInput(d.mg);
    } else {
      setMgInput('');
    }
  }

  function submitLog() {
    const mg = Number(mgInput);
    if (!mg || mg <= 0) return;
    const drinkName = selDrink === 'Custom'
      ? (customName.trim() || 'Custom')
      : selDrink;
    const timestamp = tsInput ? new Date(tsInput).getTime() : Date.now();
    setLogs(prev =>
      [...prev, { id: `${Date.now()}`, drinkName, caffeinemg: mg, timestamp }]
        .sort((a, b) => b.timestamp - a.timestamp)
    );
    setShowLog(false);
  }

  function deleteLog(id) {
    setLogs(p => p.filter(l => l.id !== id));
  }

  // ── Custom drink handlers ────────────────────────────────────────────────

  function saveCustom() {
    const mg = Number(newMgInput);
    if (!newName.trim() || !mg || mg <= 0) return;
    setCustoms(p => [...p, { id: `${Date.now()}`, name: newName.trim(), defaultMg: mg }]);
    setNewName('');
    setNewMgInput('');
    setShowAddCustom(false);
  }

  function deleteCustom(id) {
    setCustoms(p => p.filter(c => c.id !== id));
  }

  // ── Derived values ───────────────────────────────────────────────────────

  const todayLogs  = logs.filter(l => isToday(l.timestamp));
  const todayTotal = todayLogs.reduce((s, l) => s + l.caffeinemg, 0);
  const todaySt    = statusFor(todayTotal);
  const activeSt   = statusFor(active);

  const last7 = Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (6 - i));
    d.setHours(0, 0, 0, 0);
    const ds    = d.toDateString();
    const total = logs
      .filter(l => new Date(l.timestamp).toDateString() === ds)
      .reduce((s, l) => s + l.caffeinemg, 0);
    return {
      label:   i === 6 ? 'Today' : d.toLocaleDateString([], { weekday: 'short' }),
      total,
      isToday: i === 6,
    };
  });
  const maxBar = Math.max(...last7.map(d => d.total), 200);

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div
      style={{ fontFamily: "'Inter', system-ui, sans-serif" }}
      className="min-h-screen bg-gray-950 text-gray-100"
    >
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-20 bg-gray-950/95 backdrop-blur border-b border-gray-800 px-4 py-3 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold tracking-tight">Dose</h1>
          <p className="text-xs text-gray-500 leading-none mt-0.5">Caffeine Tracker</p>
        </div>
        <button
          onClick={openLogForm}
          className="bg-blue-600 hover:bg-blue-500 active:scale-95 text-white text-sm font-semibold px-4 py-2 rounded-xl transition-all"
        >
          + Log
        </button>
      </header>

      {/* ── Tabs ──────────────────────────────────────────────────────────── */}
      <nav className="flex border-b border-gray-800 px-4">
        {[['today', 'Today'], ['history', 'History'], ['drinks', 'Drinks']].map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === id
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      {/* ── Main content ──────────────────────────────────────────────────── */}
      <main className="px-4 py-5 max-w-md mx-auto space-y-4">

        {/* ════ TODAY TAB ═══════════════════════════════════════════════════ */}
        {tab === 'today' && (
          <>
            {/* Daily total + status bar */}
            <Card>
              <div className="flex items-start justify-between mb-5">
                <div>
                  <SectionLabel>Today</SectionLabel>
                  <div className="flex items-baseline gap-1.5 -mt-2">
                    <span className="text-5xl font-bold tabular-nums leading-none">{todayTotal}</span>
                    <span className="text-gray-400 text-sm">mg</span>
                  </div>
                </div>
                <span
                  className="text-xs font-semibold mt-1 px-2.5 py-1 rounded-full border"
                  style={{
                    color: todaySt.color,
                    borderColor: todaySt.ring,
                    backgroundColor: `${todaySt.ring}33`,
                  }}
                >
                  {todaySt.label}
                </span>
              </div>

              {/* Progress bar */}
              <div className="space-y-1.5">
                <div className="relative h-2.5 bg-gray-800 rounded-full overflow-hidden">
                  {/* zone markers */}
                  <div className="absolute inset-y-0 w-px bg-green-900" style={{ left: `${(200/600)*100}%` }} />
                  <div className="absolute inset-y-0 w-px bg-yellow-900" style={{ left: `${(400/600)*100}%` }} />
                  <div
                    className="absolute inset-y-0 left-0 rounded-full transition-all duration-700"
                    style={{
                      width: `${Math.min((todayTotal / 600) * 100, 100)}%`,
                      backgroundColor: todaySt.color,
                    }}
                  />
                </div>
                <div className="flex justify-between text-xs" style={{ color: '#374151' }}>
                  <span>0</span>
                  <span style={{ color: '#166534' }}>200</span>
                  <span style={{ color: '#854d0e' }}>400</span>
                  <span style={{ color: '#7f1d1d' }}>600mg</span>
                </div>
              </div>
            </Card>

            {/* Active caffeine in system */}
            <Card>
              <SectionLabel>Active in System</SectionLabel>
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  <div className="flex items-baseline gap-1.5">
                    <span
                      className="text-4xl font-bold tabular-nums leading-none"
                      style={{ color: activeSt.color }}
                    >
                      {Math.round(active)}
                    </span>
                    <span className="text-gray-400 text-sm">mg</span>
                  </div>
                  <p className="text-xs text-gray-600 mt-2">
                    5-hr half-life · live estimate
                  </p>
                  {active > 100 && (
                    <p className="text-xs text-gray-500 mt-1">
                      ~{Math.round(HALF_LIFE_HOURS * Math.log2(active / 50))}h until &lt;50mg
                    </p>
                  )}
                </div>
                <Gauge value={active} max={400} color={activeSt.color} />
              </div>
            </Card>

            {/* Today's timeline */}
            <Card>
              <SectionLabel>Today's Doses</SectionLabel>
              {todayLogs.length === 0 ? (
                <div className="py-8 text-center">
                  <p className="text-gray-600 text-sm">Nothing logged today</p>
                  <button
                    onClick={openLogForm}
                    className="text-blue-400 text-sm mt-2 hover:text-blue-300 transition-colors"
                  >
                    Log your first dose →
                  </button>
                </div>
              ) : (
                <div>
                  {todayLogs.map(log => {
                    const s = statusFor(log.caffeinemg);
                    return (
                      <div
                        key={log.id}
                        className="group flex items-center gap-3 py-3 border-b border-gray-800/50 last:border-0"
                      >
                        <div
                          className="w-1 h-9 rounded-full flex-shrink-0"
                          style={{ backgroundColor: s.color }}
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate leading-tight">{log.drinkName}</p>
                          <p className="text-xs text-gray-500 mt-0.5">{fmtTime(log.timestamp)}</p>
                        </div>
                        <span className="text-sm font-semibold tabular-nums" style={{ color: s.color }}>
                          {log.caffeinemg}mg
                        </span>
                        <button
                          onClick={() => deleteLog(log.id)}
                          className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 text-xs ml-1 transition-all w-4"
                          title="Delete"
                        >
                          ✕
                        </button>
                      </div>
                    );
                  })}
                  <div className="pt-3 text-right">
                    <span className="text-xs text-gray-600">
                      {todayLogs.length} dose{todayLogs.length !== 1 ? 's' : ''} · {todayTotal}mg total
                    </span>
                  </div>
                </div>
              )}
            </Card>
          </>
        )}

        {/* ════ HISTORY TAB ═════════════════════════════════════════════════ */}
        {tab === 'history' && (
          <>
            <Card>
              <SectionLabel>7-Day Intake</SectionLabel>

              {/* Bar chart */}
              <div className="flex items-end gap-2" style={{ height: 130 }}>
                {last7.map((day, i) => {
                  const hPct = maxBar > 0
                    ? Math.max((day.total / maxBar) * 100, day.total > 0 ? 5 : 0)
                    : 0;
                  const s = statusFor(day.total);
                  return (
                    <div key={i} className="flex-1 flex flex-col items-center justify-end gap-1">
                      {day.total > 0 && (
                        <span className="text-xs text-gray-500 tabular-nums" style={{ fontSize: 10 }}>
                          {day.total}
                        </span>
                      )}
                      <div
                        className="w-full rounded-t-md transition-all duration-500"
                        style={{
                          height: `${hPct}%`,
                          minHeight: day.total > 0 ? 6 : 0,
                          backgroundColor: day.total > 0 ? s.color : '#1f2937',
                          opacity: day.isToday ? 1 : 0.5,
                        }}
                      />
                      <span
                        className="text-xs"
                        style={{
                          color: day.isToday ? '#60a5fa' : '#4b5563',
                          fontWeight: day.isToday ? 600 : 400,
                          fontSize: 11,
                        }}
                      >
                        {day.label}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Chart legend */}
              <div className="flex gap-4 mt-4 pt-4 border-t border-gray-800">
                {[['#22c55e', '<200mg'], ['#eab308', '200–400'], ['#ef4444', '>400mg']].map(([c, l]) => (
                  <div key={l} className="flex items-center gap-1.5">
                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: c }} />
                    <span className="text-xs text-gray-500">{l}</span>
                  </div>
                ))}
              </div>
            </Card>

            {/* All log entries */}
            <Card>
              <SectionLabel>All Entries</SectionLabel>
              {logs.length === 0 ? (
                <p className="text-gray-600 text-sm text-center py-6">No entries yet</p>
              ) : (
                <div>
                  {logs.slice(0, 30).map(log => (
                    <div
                      key={log.id}
                      className="group flex items-center gap-3 py-3 border-b border-gray-800/50 last:border-0"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{log.drinkName}</p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {new Date(log.timestamp).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                          {' · '}
                          {fmtTime(log.timestamp)}
                        </p>
                      </div>
                      <span className="text-sm font-semibold text-gray-300 tabular-nums">
                        {log.caffeinemg}mg
                      </span>
                      <button
                        onClick={() => deleteLog(log.id)}
                        className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 text-xs ml-1 transition-all w-4"
                        title="Delete"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                  {logs.length > 30 && (
                    <p className="text-xs text-gray-600 text-center pt-3">
                      Showing 30 of {logs.length} entries
                    </p>
                  )}
                </div>
              )}
            </Card>
          </>
        )}

        {/* ════ DRINKS TAB ══════════════════════════════════════════════════ */}
        {tab === 'drinks' && (
          <>
            {/* Built-in presets (read-only) */}
            <Card>
              <SectionLabel>Presets</SectionLabel>
              {PRESETS.map(d => (
                <div
                  key={d.name}
                  className="flex items-center justify-between py-2.5 border-b border-gray-800/50 last:border-0"
                >
                  <span className="text-sm">{d.name}</span>
                  <span className="text-sm text-gray-500 tabular-nums">{d.mg}mg</span>
                </div>
              ))}
            </Card>

            {/* Custom drinks */}
            <Card>
              <div className="flex items-center justify-between mb-4">
                <SectionLabel>Custom Drinks</SectionLabel>
                <button
                  onClick={() => setShowAddCustom(s => !s)}
                  className="text-blue-400 text-xs hover:text-blue-300 transition-colors -mt-4"
                >
                  {showAddCustom ? 'Cancel' : '+ Add'}
                </button>
              </div>

              {showAddCustom && (
                <div className="mb-4 p-4 bg-gray-800 rounded-xl space-y-3">
                  <Input
                    type="text"
                    placeholder="Drink name"
                    value={newName}
                    onChange={e => setNewName(e.target.value)}
                  />
                  <Input
                    type="number"
                    placeholder="Caffeine (mg)"
                    value={newMgInput}
                    onChange={e => setNewMgInput(e.target.value)}
                    min="1"
                  />
                  <button
                    onClick={saveCustom}
                    className="w-full bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium py-2.5 rounded-xl transition-colors"
                  >
                    Save Drink
                  </button>
                </div>
              )}

              {customs.length === 0 ? (
                <p className="text-gray-600 text-sm text-center py-4">
                  No custom drinks yet
                </p>
              ) : (
                customs.map(d => (
                  <div
                    key={d.id}
                    className="flex items-center justify-between py-2.5 border-b border-gray-800/50 last:border-0"
                  >
                    <span className="text-sm">{d.name}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-gray-500 tabular-nums">{d.defaultMg}mg</span>
                      <button
                        onClick={() => deleteCustom(d.id)}
                        className="text-gray-600 hover:text-red-400 text-xs transition-colors"
                        title="Delete"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ))
              )}
            </Card>
          </>
        )}
      </main>

      {/* ── Log Modal ─────────────────────────────────────────────────────── */}
      {showLog && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
          style={{ backgroundColor: 'rgba(0,0,0,0.75)' }}
          onClick={e => { if (e.target === e.currentTarget) setShowLog(false); }}
        >
          <div className="bg-gray-900 rounded-2xl w-full max-w-md border border-gray-800 p-5 space-y-5">
            {/* Modal header */}
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">Log a Dose</h2>
              <button
                onClick={() => setShowLog(false)}
                className="text-gray-500 hover:text-gray-300 text-xl leading-none transition-colors"
              >
                ×
              </button>
            </div>

            {/* Drink picker */}
            <div>
              <label className="text-xs text-gray-500 uppercase tracking-widest block mb-2">
                Drink
              </label>
              <div className="flex flex-wrap gap-2">
                {[...allDrinks, { name: 'Custom', mg: 0 }].map(d => (
                  <button
                    key={d.name}
                    onClick={() => pickDrink(d.name)}
                    className={`px-3 py-1.5 rounded-xl text-sm font-medium transition-colors ${
                      selDrink === d.name
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                    }`}
                  >
                    {d.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Custom name input */}
            {selDrink === 'Custom' && (
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-widest block mb-2">
                  Name (optional)
                </label>
                <Input
                  type="text"
                  placeholder="e.g. Cold Brew"
                  value={customName}
                  onChange={e => setCustomName(e.target.value)}
                />
              </div>
            )}

            {/* Caffeine amount */}
            <div>
              <label className="text-xs text-gray-500 uppercase tracking-widest block mb-2">
                Caffeine (mg)
              </label>
              <Input
                type="number"
                value={mgInput}
                onChange={e => setMgInput(e.target.value)}
                min="1"
              />
            </div>

            {/* Timestamp */}
            <div>
              <label className="text-xs text-gray-500 uppercase tracking-widest block mb-2">
                Time
              </label>
              <Input
                type="datetime-local"
                value={tsInput}
                onChange={e => setTsInput(e.target.value)}
              />
            </div>

            <button
              onClick={submitLog}
              className="w-full bg-blue-600 hover:bg-blue-500 active:scale-98 text-white font-semibold py-3 rounded-xl transition-all"
            >
              Log Dose
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
