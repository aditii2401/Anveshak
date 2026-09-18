import React, { useState, useRef, useEffect } from 'react';
import { Sparkles, Send, Phone, Landmark, Car, FileText, AlertTriangle, RotateCcw } from 'lucide-react';

export interface ForensicEntity {
  id: string;
  name: string;
  initials: string;
  type: string;
  pid: string;
  role: string;
  aliases: string[];
  association: string;
  locations: string[];
  confidence: number;
  centrality: 'High' | 'Medium' | 'Low';
  evidence: Array<{ src: string; rec: string; rel: string }>;
  alerts: Array<{ t: string; s: string }>;
}

export const ENTITY_DATABASE: Record<string, ForensicEntity> = {
  arjun: {
    id: 'arjun',
    name: 'Arjun Rathore',
    initials: 'AR',
    type: 'Person of interest',
    pid: 'P-017',
    role: 'Cash movement & coordination',
    aliases: ['A. Rathore', 'Arjun Bhai'],
    association: 'Rathore Transport Services (director)',
    locations: ['Nagpur', 'Bhandara', 'Raipur'],
    confidence: 0.91,
    centrality: 'High',
    evidence: [
      { src: 'FIR', rec: 'FIR_case_102', rel: 'Named person under Sec 420/120B' },
      { src: 'CDR', rec: 'CDR_1182', rel: 'Phone interaction (42 calls)' },
      { src: 'FIN', rec: 'TXN_44S1', rel: 'Account transfer (₹18.4L cyclic)' },
    ],
    alerts: [
      { t: 'Communication spike with Vikram Patil', s: '42 calls in 6 hrs' },
      { t: 'Cyclic transfer across 5 accounts', s: '₹18.4L over 11 days' },
    ],
  },
  vikram: {
    id: 'vikram',
    name: 'Vikram Patil',
    initials: 'VP',
    type: 'Account holder',
    pid: 'P-009',
    role: 'Account transfer · 4 occurrences',
    aliases: ['V. Patil', 'Vicky'],
    association: 'Arjun Rathore (frequent contact)',
    locations: ['Nagpur', 'Raipur'],
    confidence: 0.88,
    centrality: 'Medium',
    evidence: [
      { src: 'FIN', rec: 'TXN_2210', rel: 'Pass-through fund transfer' },
      { src: 'CDR', rec: 'CDR_0871', rel: 'Phone interaction with prime bridge' },
    ],
    alerts: [
      { t: 'Communication spike with Arjun Rathore', s: '42 calls in 6 hrs' },
      { t: 'Rapid cash withdrawal at unlinked branch', s: '₹6.2L in cash · Raipur branch' },
    ],
  },
};

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  text: string;
  entity?: ForensicEntity;
  citations?: Array<{ label: string; doc: string }>;
  suggestedFollowups?: [string, string] | [string];
}

const GHOST_SUGGESTIONS = [
  'Investigate Arjun Rathore',
  "What is Vikram Patil's connection to the ₹18.4L transfer?",
  'Trace phone calls between Arjun and Vikram',
  'Check Rathore Transport Services shell company',
];

export const InvestigateView: React.FC = () => {
  const [inputText, setInputText] = useState('');
  const [suggestionIndex, setSuggestionIndex] = useState(0);
  const [isThinking, setIsThinking] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages, isThinking]);

  useEffect(() => {
    const interval = setInterval(() => {
      setSuggestionIndex((prev) => (prev + 1) % GHOST_SUGGESTIONS.length);
    }, 4500);
    return () => clearInterval(interval);
  }, []);

  const currentGhostSuggestion = GHOST_SUGGESTIONS[suggestionIndex];

  const handleSendMessage = (queryToSend?: string) => {
    const query = (queryToSend || inputText).trim();
    if (!query) return;

    const userMsg: ChatMessage = {
      id: `msg-user-${Date.now()}`,
      sender: 'user',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      text: query,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setIsThinking(true);

    const qLower = query.toLowerCase();
    let matchedEntity: ForensicEntity | undefined;
    if (qLower.includes('arjun') || qLower.includes('rathore')) {
      matchedEntity = ENTITY_DATABASE['arjun'];
    } else if (qLower.includes('vikram') || qLower.includes('patil')) {
      matchedEntity = ENTITY_DATABASE['vikram'];
    }

    setTimeout(() => {
      let replyText = '';
      let followups: [string, string] | [string] = [
        'Examine bilateral CDR records',
        'Verify registered vehicle telemetry',
      ];
      let citations: Array<{ label: string; doc: string }> = [];

      if (matchedEntity) {
        if (matchedEntity.id === 'arjun') {
          replyText = `Identity resolved for Arjun Rathore (PID: P-017). He acts as the core coordinating bridge in Case 24/2026. Automated cross-referencing indicates 42 telephonic interactions with Vikram Patil across 6 hours immediately preceding the ₹18.4L fund liquidation.`;
          followups = [
            'Trace the 42 calls between Arjun and Vikram',
            'Show bank transfers to Rathore Transport Services',
          ];
          citations = [
            { label: 'CDR', doc: 'Bilateral Call Log #1182 (42 calls)' },
            { label: 'FIN', doc: 'Axis-to-SBI Tranche #44S1' },
            { label: 'FIR', doc: 'FIR Case 102 / IPC Sec 420' },
          ];
        } else {
          replyText = `Vikram Patil (PID: P-009) is identified as a secondary account holder and transit mule. Financial telemetry reveals he received pass-through credits totaling ₹18.4L in SBI account ...9981.`;
          followups = [
            'Audit the Raipur branch cash withdrawals',
            'Cross-reference Vikram’s vehicle movements',
          ];
          citations = [{ label: 'FIN', doc: 'TXN-2210 Raipur Branch Cash Voucher' }];
        }
      } else {
        replyText = `Query processed against active docket Case 24/2026. The neural engine identified correlated evidence points across telecommunications and bank records.`;
        followups = ['Investigate Arjun Rathore', 'What is Vikram Patil’s connection to the transfer?'];
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `msg-bot-${Date.now()}`,
          sender: 'assistant',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          text: replyText,
          entity: matchedEntity,
          citations,
          suggestedFollowups: followups,
        },
      ]);
      setIsThinking(false);
    }, 700);
  };

  return (
    <div className="flex flex-col min-h-[calc(100vh-140px)] max-w-5xl mx-auto pb-6">
      {/* Clean heading and introduction only */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-[#fffefb] border border-[#ddd6c6] rounded-xl px-5 py-3.5 shadow-2xs mb-4">
        <div>
          <h1 className="font-serif font-bold text-slate-900 text-base tracking-tight">
            AI Case Intelligence Interrogation
          </h1>
          <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">
            Cross-examine all ingested FIR dockets, call records, bank ledgers, and vehicle tracking logs through direct inquiry.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-center">
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-bold bg-[#e1ecdf] text-[#2d5c3f]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#3d6b53] animate-pulse" />
            Active Copilot
          </span>
          <button
            type="button"
            onClick={() => setMessages([])}
            title="Clear inquiry session"
            className="p-1.5 text-slate-500 hover:text-slate-900 rounded-md hover:bg-[#f4f0e6] transition-colors cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Results Canvas */}
      <div ref={chatContainerRef} className="flex-1 overflow-y-auto space-y-6 pr-1 pb-24">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
            {msg.sender === 'user' ? (
              <div className="max-w-[85%] sm:max-w-[70%] bg-[#182029] text-white rounded-2xl rounded-tr-xs px-4 py-2.5 shadow-sm">
                <p className="text-xs leading-relaxed">{msg.text}</p>
                <div className="text-[10px] text-slate-400 text-right mt-1 font-mono">{msg.timestamp}</div>
              </div>
            ) : (
              <div className="w-full space-y-3.5">
                <div className="bg-[#fffefb] border border-[#ddd6c6] rounded-2xl rounded-tl-xs p-5 shadow-2xs space-y-4">
                  <div className="flex items-center justify-between border-b border-[#ece6d8] pb-2.5">
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-lg bg-[#f4ece1] text-[#a94e2c] flex items-center justify-center font-bold text-xs">
                        <Sparkles className="w-3.5 h-3.5" />
                      </div>
                      <span className="text-xs font-bold text-slate-900 tracking-tight">ANVESHAK Neural Synthesis</span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-400">{msg.timestamp}</span>
                  </div>

                  <p className="text-xs text-slate-800 leading-relaxed">{msg.text}</p>

                  {msg.entity && (
                    <div className="mt-4 border border-[#e4ddcd] bg-[#faf8f4] rounded-xl p-4 space-y-3.5">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#e8e2d4] pb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-11 h-11 rounded-xl bg-[#182029] text-white flex items-center justify-center font-serif font-bold text-base shadow-xs shrink-0">
                            {msg.entity.initials}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <h4 className="font-serif text-base font-bold text-slate-900 tracking-tight">{msg.entity.name}</h4>
                              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#ede8dc] text-slate-700">{msg.entity.pid}</span>
                            </div>
                            <p className="text-[11px] text-slate-600 font-medium">{msg.entity.role}</p>
                          </div>
                        </div>
                        <span className="px-2.5 py-1 rounded-md text-[11px] font-bold bg-[#f3ded2] text-[#8a3e21]">
                          Confidence: {(msg.entity.confidence * 100).toFixed(0)}%
                        </span>
                      </div>

                      {msg.entity.evidence.length > 0 && (
                        <div className="space-y-1.5">
                          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Cross-Evidence Corroboration</span>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {msg.entity.evidence.map((ev, idx) => (
                              <div key={idx} className="flex items-center gap-2 p-2 bg-[#fffefb] border border-[#e8e2d4] rounded-lg text-xs">
                                <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-[#182029] text-white">{ev.src}</span>
                                <span className="font-mono text-[11px] text-slate-700 font-semibold">{ev.rec}:</span>
                                <span className="text-slate-600 truncate text-[11px]">{ev.rel}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {msg.citations && msg.citations.length > 0 && (
                    <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-[#ece6d8]">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Citations:</span>
                      {msg.citations.map((c, i) => (
                        <span key={i} className="px-2 py-0.5 rounded bg-[#f0ecdf] text-slate-700 text-[10px] font-mono font-medium">
                          [{c.label}] {c.doc}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {msg.suggestedFollowups && msg.suggestedFollowups.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 pt-1 pl-1">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Suggested Lead:</span>
                    {msg.suggestedFollowups.slice(0, 2).map((lead, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => handleSendMessage(lead)}
                        className="inline-flex items-center gap-1.5 px-3 py-1 bg-[#fffefb] hover:bg-[#ede7d8] border border-[#ddd6c6] rounded-full text-xs font-medium text-slate-800 transition-all cursor-pointer shadow-2xs group"
                      >
                        <span className="text-[#a94e2c] group-hover:translate-x-0.5 transition-transform">↳</span>
                        <span>{lead}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {isThinking && (
          <div className="flex items-center gap-2 p-4 bg-[#fffefb] border border-[#ddd6c6] rounded-2xl rounded-tl-xs w-64 shadow-2xs">
            <Sparkles className="w-4 h-4 text-[#a94e2c] animate-spin" />
            <span className="text-xs text-slate-600 font-medium animate-pulse">Cross-correlating evidence...</span>
          </div>
        )}
      </div>

      {/* Sticky Bottom Prompt Bar */}
      <div className="sticky bottom-0 z-20 pt-3">
        <div className="relative max-w-3xl mx-auto w-full bg-[#fffefb]/95 backdrop-blur-md border border-[#c8beaa] rounded-2xl shadow-lg p-2 transition-all focus-within:border-slate-800">
          <div className="relative flex items-center">
            <div className="pl-3 text-[#a94e2c]">
              <Sparkles className="w-4 h-4" />
            </div>

            <input
              ref={inputRef}
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleSendMessage();
                } else if (e.key === 'Tab' && !inputText) {
                  e.preventDefault();
                  setInputText(currentGhostSuggestion);
                }
              }}
              className="w-full pl-3 pr-24 py-2.5 bg-transparent text-xs text-slate-900 placeholder:text-transparent focus:outline-none font-medium z-10"
              placeholder="Inquire..."
              autoFocus
            />

            {!inputText && (
              <div
                onClick={() => {
                  setInputText(currentGhostSuggestion);
                  inputRef.current?.focus();
                }}
                className="absolute left-10 text-xs text-[#1e242b]/40 pointer-events-auto cursor-pointer truncate max-w-[calc(100%-120px)] select-none font-medium flex items-center gap-1.5"
              >
                <span>{currentGhostSuggestion}</span>
                <span className="text-[9px] px-1.5 py-0.2 rounded border border-[#1e242b]/20 text-[#1e242b]/50 hidden sm:inline font-mono">
                  Tab ⇥
                </span>
              </div>
            )}

            <div className="absolute right-1.5 flex items-center gap-1 z-20">
              <button
                type="button"
                onClick={() => handleSendMessage()}
                disabled={!inputText.trim()}
                className={`p-2 rounded-xl transition-all cursor-pointer flex items-center justify-center ${
                  inputText.trim()
                    ? 'bg-[#182029] text-white hover:bg-slate-800 shadow-xs'
                    : 'bg-[#ede8dc] text-slate-400 cursor-not-allowed'
                }`}
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default InvestigateView;