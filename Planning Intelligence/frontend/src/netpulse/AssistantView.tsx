// src/netpulse/AssistantView.tsx - the OCTO tab.
//
// Ollama-only tool-calling agent (see backend/agent.py). The model reads
// your text, picks zero or more tools, backend/agent.py's TOOL_IMPLS
// compute the real answer straight from the pipeline, and the model
// only phrases the final sentence. The sector-level clash explainer
// used to live here but belongs with the rest of the Clashes tooling -
// see ClashesView.tsx.
import { useEffect, useRef, useState } from 'react';
import { Bot, Send, Wrench, ChevronDown, ChevronUp, Cpu, Sparkles, Database, Radar, Search, MapPin, BarChart3, Ruler, Compass, BookOpen, Zap } from 'lucide-react';
import { api, type ToolCall } from './api';
import { Card, FeatureCard, AccentHeader } from './ui';
import octoMark from '../imports/octo-mark.svg';

type ChatMsg = { role: 'user' | 'assistant'; text: string; toolCalls?: ToolCall[] };

function loadAssistantSession(workbook: string): { messages: ChatMsg[]; input: string } {
  try {
    const raw = localStorage.getItem(`netpulse-assistant:${workbook}`);
    if (!raw) return { messages: [], input: '' };
    const parsed = JSON.parse(raw);
    return {
      messages: Array.isArray(parsed?.messages) ? parsed.messages : [],
      input: typeof parsed?.input === 'string' ? parsed.input : '',
    };
  } catch {
    return { messages: [], input: '' };
  }
}

const TOOL_META: Record<string, { icon: any; category: string; color: string }> = {
  explain_sector: { icon: Zap, category: 'Lookup', color: '#1565C0' },
  find_sites: { icon: Search, category: 'Lookup', color: '#1565C0' },
  region_summary: { icon: BarChart3, category: 'Analysis', color: '#00838F' },
  overall_summary: { icon: BarChart3, category: 'Analysis', color: '#00838F' },
  worst_sites: { icon: Compass, category: 'Analysis', color: '#00838F' },
  plan_health_score: { icon: Zap, category: 'Analysis', color: '#00838F' },
  compare_regions: { icon: BarChart3, category: 'Analysis', color: '#00838F' },
  distance_between: { icon: Ruler, category: 'Geometry', color: '#7C3AED' },
  neighbors_within_radius: { icon: MapPin, category: 'Geometry', color: '#7C3AED' },
  clash_type_info: { icon: BookOpen, category: 'Reference', color: '#B45309' },
};
const CATEGORY_ORDER = ['Lookup', 'Analysis', 'Geometry', 'Reference'];

function OctoMark({ className = 'w-20 h-20' }: { className?: string }) {
  return (
    <img src={octoMark} alt="OCTO" className={className} />
  );
}

function Markdown({ text }: { text: string }) {
  const lines = text.split('\n');
  return (
    <div className="space-y-1">
      {lines.map((line, i) => {
        const parts = line.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
        return (
          <div key={i}>
            {parts.map((part, j) =>
              part.startsWith('**') && part.endsWith('**')
                ? <strong key={j} className="font-semibold text-[var(--color-text)]">{part.slice(2, -2)}</strong>
                : <span key={j}>{part}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ToolCallChip({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false);
  const args = Object.entries(call.input);
  return (
    <div className="border border-primary/20 bg-primary/5 rounded-lg overflow-hidden text-xs">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-primary/10 transition-colors">
        <div className="w-5 h-5 rounded-full bg-primary flex items-center justify-center shrink-0">
          <Wrench className="w-2.5 h-2.5 text-white" />
        </div>
        <span className="font-mono font-semibold text-primary">{call.name}</span>
        {args.map(([k, v]) => (
          <span key={k} className="font-mono text-[10px] bg-white border border-primary/20 rounded-full px-2 py-0.5 text-gray-500">
            {k}={JSON.stringify(v)}
          </span>
        ))}
        {open ? <ChevronUp className="w-3 h-3 ml-auto text-gray-400 shrink-0" /> : <ChevronDown className="w-3 h-3 ml-auto text-gray-400 shrink-0" />}
      </button>
      {open && (
        <pre className="px-3 pb-2.5 pt-1 text-[10px] overflow-auto max-h-48 text-gray-600 bg-white/60 border-t border-primary/10">
          {JSON.stringify(call.result, null, 2)}
        </pre>
      )}
    </div>
  );
}

const THINKING_STEPS = [
  { icon: Radar, text: 'Scanning the request...' },
  { icon: Database, text: 'Querying live network data...' },
  { icon: Sparkles, text: 'Putting the answer together...' },
];

function ThinkingCard() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setStep((s) => (s + 1) % THINKING_STEPS.length), 1400);
    return () => clearInterval(id);
  }, []);
  const Icon = THINKING_STEPS[step].icon;
  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-3 bg-gradient-to-r from-primary/10 to-secondary/10 border border-primary/20 rounded-xl px-4 py-3 max-w-[85%]">
        <div className="relative w-8 h-8 shrink-0">
          <div className="absolute inset-0 rounded-full bg-primary/20 animate-ping" />
          <div className="relative w-8 h-8 rounded-full bg-primary flex items-center justify-center">
            <Icon className="w-4 h-4 text-white" />
          </div>
        </div>
        <div>
          <div className="text-sm font-medium text-[var(--color-text)]">{THINKING_STEPS[step].text}</div>
          <div className="flex gap-1 mt-1">
            {THINKING_STEPS.map((_, i) => (
              <span key={i} className={`h-1 rounded-full transition-all duration-300 ${i === step ? 'w-5 bg-primary' : 'w-1.5 bg-primary/30'}`} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function AssistantView({ workbook }: { workbook: string }) {
  const [tools, setTools] = useState<{ name: string; description: string }[]>([]);
  const [agentModel, setAgentModel] = useState<string | null>(null);

  useEffect(() => { api.agentTools().then(setTools).catch(() => {}); }, []);
  useEffect(() => { api.agentInfo().then((info) => setAgentModel(info.model)).catch(() => setAgentModel(null)); }, []);

  const [messages, setMessages] = useState<ChatMsg[]>(() => loadAssistantSession(workbook).messages);
  const [input, setInput] = useState(() => loadAssistantSession(workbook).input);
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const saved = loadAssistantSession(workbook);
    setMessages(saved.messages);
    setInput(saved.input);
    setSending(false);
  }, [workbook]);

  useEffect(() => {
    localStorage.setItem(`netpulse-assistant:${workbook}`, JSON.stringify({ messages, input }));
  }, [workbook, messages, input]);

  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }); }, [messages, sending]);

  const send = async () => {
    if (!input.trim()) return;
    const q = input.trim();
    setInput('');
    setMessages((cur) => [...cur, { role: 'user', text: q }]);
    setSending(true);
    try {
      const history = messages.map((m) => ({ role: m.role, content: m.text }));
      const out = await api.agentChat(workbook, q, 'ollama', history);
      setMessages((cur) => [...cur, { role: 'assistant', text: out.reply, toolCalls: out.tool_calls }]);
    } catch (e) {
      setMessages((cur) => [...cur, { role: 'assistant', text: `Error: ${e}` }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
        <FeatureCard className="p-5 flex flex-col h-[640px]">
          <div className="rounded-3xl border border-primary/15 bg-white/85 p-4 shadow-sm">
            <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] items-center gap-4">
              <div className="flex items-center gap-4">
                <div className="rounded-3xl border border-primary/15 bg-gradient-to-br from-white to-primary/5 p-3 shadow-sm shrink-0">
                  <OctoMark className="w-20 h-20" />
                </div>
                <div className="space-y-2">
                  <div className="inline-flex items-center rounded-full border border-primary/15 bg-primary/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-primary">
                    OCTO Console
                  </div>
                  <div className="text-lg font-bold text-slate-800">AI Network Tool Orchestrator</div>
                  <div className="text-xs leading-relaxed text-slate-600 max-w-sm">Orchestrated Cellular Telecom Operations for live workbook analysis, clash reasoning, validation, and network answers.</div>
                </div>
              </div>

              <div className="space-y-2 md:text-right">
                <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-primary">One Agent. Many Tools. One Answer.</div>
                <div className="flex md:justify-end">
                  <div className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-gray-500 shadow-sm">
                    <Cpu className="w-3.5 h-3.5 text-gray-400" />
                    {agentModel ? <span className="font-mono">{agentModel}</span> : <span className="text-gray-400">checking model...</span>}
                  </div>
                </div>
                <div className="flex gap-2 md:justify-end flex-wrap">
                  <span className="rounded-full border border-secondary/20 bg-secondary/10 px-2.5 py-1 text-[10px] font-semibold text-[var(--color-secondary)]">Live tools</span>
                  <span className="rounded-full border border-primary/15 bg-primary/10 px-2.5 py-1 text-[10px] font-semibold text-primary">Workbook-grounded</span>
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between mb-3 mt-4 pb-3 border-b border-[var(--color-border)]">
            <div className="flex items-center gap-2 text-sm font-semibold"><Bot className="w-4 h-4 text-primary" /> OCTO Conversation</div>
            <div className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-semibold text-slate-600 shadow-sm">Workbook-grounded replies</div>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-3 pr-1">
            {messages.length === 0 && !sending && (
              <div className="h-full flex flex-col items-center justify-center text-center gap-2 text-gray-400">
                <div className="w-20 h-20 rounded-3xl border border-primary/15 bg-white/80 flex items-center justify-center shadow-sm">
                  <OctoMark className="w-14 h-14" />
                </div>
                <div className="text-sm font-semibold text-slate-700">OCTO is ready</div>
                <p className="text-xs max-w-xs">Try "why does ALX3282-1 clash?" or "how bad is Sinai?" or "distance between ALX3282 and ALX3290"</p>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {m.role === 'assistant' ? (
                  <div className="max-w-[85%] bg-white border border-[var(--color-border)] rounded-xl rounded-tl-sm shadow-sm overflow-hidden">
                    <div className="flex items-center gap-2 px-3 pt-2.5 pb-1">
                      <div className="w-6 h-6 rounded-full border border-primary/15 bg-white flex items-center justify-center shrink-0 shadow-sm overflow-hidden">
                        <OctoMark className="w-5 h-5" />
                      </div>
                      <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide">OCTO</span>
                    </div>
                    <div className="px-3 pb-3 text-sm text-[var(--color-text)]">
                      <Markdown text={m.text} />
                    </div>
                    {m.toolCalls && m.toolCalls.length > 0 && (
                      <div className="px-3 pb-3 space-y-1.5">{m.toolCalls.map((tc, j) => <ToolCallChip key={j} call={tc} />)}</div>
                    )}
                  </div>
                ) : (
                  <div className="max-w-[85%] bg-primary text-white rounded-xl rounded-tr-sm px-3.5 py-2.5 text-sm shadow-sm">
                    {m.text}
                  </div>
                )}
              </div>
            ))}
            {sending && <ThinkingCard />}
          </div>

          <div className="flex gap-2 mt-3 pt-3 border-t border-[var(--color-border)]">
            <input
              value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
              placeholder='Ask OCTO anything about this network...'
              className="flex-1 border border-[var(--color-border)] rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <button onClick={send} disabled={sending || !input.trim()} className="bg-primary text-white w-10 h-10 rounded-full disabled:opacity-50 flex items-center justify-center shrink-0 hover:opacity-90 transition-opacity">
              <Send className="w-4 h-4" />
            </button>
          </div>
        </FeatureCard>

        <FeatureCard className="p-0 h-fit overflow-hidden">
          <div className="p-3">
            <AccentHeader
              title="OCTO Toolset"
              subtitle={`${tools.length} live tools · many capabilities, one orchestrator`}
              actions={<div className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-primary" /><span className="h-2.5 w-2.5 rounded-full bg-secondary" /><span className="h-2.5 w-2.5 rounded-full bg-slate-400" /></div>}
            />
          </div>

          <div className="p-3 max-h-[560px] overflow-y-auto space-y-4">
            {tools.length === 0 && <p className="text-xs text-gray-400 p-2">Loading...</p>}
            {CATEGORY_ORDER.map((cat) => {
              const inCat = tools.filter((t) => (TOOL_META[t.name]?.category || 'Reference') === cat);
              if (!inCat.length) return null;
              return (
                <div key={cat}>
                  <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 px-1 mb-1.5">{cat}</div>
                  <div className="space-y-1.5">
                    {inCat.map((t) => {
                      const meta = TOOL_META[t.name] || { icon: Wrench, color: '#64748B' };
                      const Icon = meta.icon;
                      return (
                        <div key={t.name} className="group flex gap-2.5 p-2 rounded-lg border border-transparent hover:border-[var(--color-border)] hover:bg-gray-50 transition-all">
                          <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5" style={{ background: `${meta.color}1A` }}>
                            <Icon className="w-3.5 h-3.5" style={{ color: meta.color }} />
                          </div>
                          <div className="min-w-0">
                            <div className="text-xs font-mono font-semibold" style={{ color: meta.color }}>{t.name}</div>
                            <div className="text-[11px] text-gray-500 mt-0.5 leading-snug">{t.description.split('.')[0]}.</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </FeatureCard>
      </div>
    </div>
  );
}