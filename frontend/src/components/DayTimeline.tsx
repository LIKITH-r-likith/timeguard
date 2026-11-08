import React, { useState } from 'react';
import type { Shift, Punch, TimecardChange, ExceptionType } from '../types';

interface DayTimelineProps {
  workDate: string;
  shifts: Shift[];
  punches: Punch[];
  exceptionType?: ExceptionType;
  highlightedEvidenceId?: string | null;
  proposedChanges?: TimecardChange[];
  onSelectEvidence?: (id: string) => void;
}

export const DayTimeline: React.FC<DayTimelineProps> = ({
  workDate,
  shifts,
  punches,
  exceptionType,
  highlightedEvidenceId,
  proposedChanges = [],
  onSelectEvidence,
}) => {
  const [hoveredItem, setHoveredItem] = useState<{ label: string; x: number; y: number } | null>(null);

  // Timeline bounds: 06:00 to 22:00 (16 hours = 960 minutes)
  const START_HOUR = 6;
  const END_HOUR = 22;
  const TOTAL_HOURS = END_HOUR - START_HOUR;
  const TOTAL_MINUTES = TOTAL_HOURS * 60;

  const SVG_WIDTH = 800;
  const SVG_HEIGHT = 200;
  const PADDING_X = 50;
  const DRAW_WIDTH = SVG_WIDTH - PADDING_X * 2;

  // Convert an ISO timestamp to x coordinate
  const timeToX = (isoString: string): number => {
    try {
      const d = new Date(isoString);
      const minutes = d.getHours() * 60 + d.getMinutes();
      const offsetMinutes = minutes - START_HOUR * 60;
      const clamped = Math.max(0, Math.min(TOTAL_MINUTES, offsetMinutes));
      return PADDING_X + (clamped / TOTAL_MINUTES) * DRAW_WIDTH;
    } catch {
      return PADDING_X;
    }
  };

  // Filter shifts and punches for this work date
  const dayShifts = shifts.filter((s) => s.start.startsWith(workDate));
  const dayPunches = punches
    .filter((p) => p.at.startsWith(workDate))
    .sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());

  // Hours array for tick marks
  const hours = Array.from({ length: TOTAL_HOURS + 1 }, (_, i) => START_HOUR + i);

  // Detect if an OUT punch exists
  const hasOutPunch = dayPunches.some((p) => p.type === 'OUT');
  const primaryShift = dayShifts[0];

  return (
    <div className="w-full bg-slate-900 border border-slate-800 rounded-xl p-4 text-slate-100 shadow-inner">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3 pb-2 border-b border-slate-800 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-300">Timeline:</span>
          <span className="font-mono text-indigo-400 font-medium">{workDate}</span>
          <span className="text-slate-500">|</span>
          <span className="text-slate-400">Hours 06:00 – 22:00</span>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-300">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-2 bg-indigo-500/40 border border-indigo-400 rounded-sm"></span>
            <span>Shift</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-2 bg-emerald-500/80 rounded-sm"></span>
            <span>Punched Work</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-2 bg-amber-500/50 rounded-sm"></span>
            <span>Break</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-2 bg-amber-900/40 border border-amber-600 border-dashed rounded-sm"></span>
            <span>Overtime Zone (&gt;8h)</span>
          </div>
          {exceptionType === 'MISSED_PUNCH' && !hasOutPunch && (
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 ring-2 ring-rose-400"></span>
              <span className="text-rose-400 font-semibold">Missed Punch</span>
            </div>
          )}
        </div>
      </div>

      <div className="relative overflow-x-auto">
        <svg
          viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
          className="w-full h-auto select-none min-w-[650px]"
          data-testid="day-timeline-svg"
        >
          <defs>
            {/* Overtime stripe pattern */}
            <pattern id="overtime-stripes" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="4" height="8" fill="#78350f" fillOpacity="0.4" />
              <rect x="4" width="4" height="8" fill="#b45309" fillOpacity="0.2" />
            </pattern>
          </defs>

          {/* Background Grid & Hour Ticks */}
          {hours.map((h) => {
            const x = PADDING_X + ((h - START_HOUR) / TOTAL_HOURS) * DRAW_WIDTH;
            return (
              <g key={`hour-${h}`}>
                <line x1={x} y1={25} x2={x} y2={SVG_HEIGHT - 35} stroke="#334155" strokeWidth={1} strokeDasharray="3 3" />
                <text x={x} y={SVG_HEIGHT - 18} fill="#94a3b8" fontSize="10" textAnchor="middle" fontFamily="monospace">
                  {String(h).padStart(2, '0')}:00
                </text>
              </g>
            );
          })}

          {/* Track Labels */}
          <text x={12} y={55} fill="#94a3b8" fontSize="10" fontWeight="600" textAnchor="start">
            SCHEDULE
          </text>
          <text x={12} y={115} fill="#94a3b8" fontSize="10" fontWeight="600" textAnchor="start">
            ACTUAL
          </text>

          {/* OVERTIME ZONE (>8 hours threshold, typically starting at 17:00) */}
          {primaryShift && (
            <g data-testid="overtime-zone">
              {(() => {
                const shiftStart = new Date(primaryShift.start);
                // 8 hours after shift start
                const otStart = new Date(shiftStart.getTime() + 8 * 60 * 60 * 1000);
                const otX = timeToX(otStart.toISOString());
                const endX = PADDING_X + DRAW_WIDTH;
                const width = Math.max(0, endX - otX);
                return (
                  <>
                    <rect
                      x={otX}
                      y={30}
                      width={width}
                      height={100}
                      fill="url(#overtime-stripes)"
                      stroke="#d97706"
                      strokeWidth={1}
                      strokeDasharray="4 2"
                      rx={4}
                    />
                    <text x={otX + 8} y={42} fill="#fbbf24" fontSize="9" fontWeight="bold">
                      OVERTIME ZONE (&gt;8h)
                    </text>
                  </>
                );
              })()}
            </g>
          )}

          {/* SCHEDULED SHIFTS TRACK (Y: 45, Height: 30) */}
          {dayShifts.map((shift) => {
            const x1 = timeToX(shift.start);
            const x2 = timeToX(shift.end);
            const width = Math.max(8, x2 - x1);
            const isHighlighted = highlightedEvidenceId === shift.id;

            return (
              <g
                key={shift.id}
                data-testid={`shift-${shift.id}`}
                className="cursor-pointer"
                onClick={() => onSelectEvidence && onSelectEvidence(shift.id)}
                onMouseEnter={() =>
                  setHoveredItem({
                    label: `Shift: ${new Date(shift.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${new Date(shift.end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} (${shift.id})`,
                    x: (x1 + x2) / 2,
                    y: 40,
                  })
                }
                onMouseLeave={() => setHoveredItem(null)}
              >
                <rect
                  x={x1}
                  y={45}
                  width={width}
                  height={28}
                  rx={4}
                  fill={isHighlighted ? '#4338ca' : '#1e1b4b'}
                  stroke={isHighlighted ? '#a5b4fc' : '#6366f1'}
                  strokeWidth={isHighlighted ? 2.5 : 1.5}
                />
                <text
                  x={x1 + 8}
                  y={63}
                  fill="#c7d2fe"
                  fontSize="10"
                  fontWeight="600"
                  className="pointer-events-none"
                >
                  Shift ({new Date(shift.start).getHours()}:00 - {new Date(shift.end).getHours()}:00)
                </text>
              </g>
            );
          })}

          {/* ACTUAL WORK INTERVALS TRACK (Y: 100, Height: 28) */}
          {(() => {
            // Pair up IN/OUT and BREAK_START/BREAK_END
            const intervals: { start: string; end: string; type: 'work' | 'break' }[] = [];
            let inPunch: Punch | null = null;
            let breakStart: Punch | null = null;

            for (const p of dayPunches) {
              if (p.type === 'IN') {
                inPunch = p;
              } else if (p.type === 'BREAK_START' && inPunch) {
                intervals.push({ start: inPunch.at, end: p.at, type: 'work' });
                breakStart = p;
                inPunch = null;
              } else if (p.type === 'BREAK_END') {
                if (breakStart) {
                  intervals.push({ start: breakStart.at, end: p.at, type: 'break' });
                  breakStart = null;
                }
                inPunch = p;
              } else if (p.type === 'OUT' && inPunch) {
                intervals.push({ start: inPunch.at, end: p.at, type: 'work' });
                inPunch = null;
              }
            }

            // Open interval if currently clocked in without out punch
            if (inPunch) {
              // Draw work interval up to 17:00 or current
              const endApprox = primaryShift ? primaryShift.end : inPunch.at;
              intervals.push({ start: inPunch.at, end: endApprox, type: 'work' });
            }

            return intervals.map((interval, idx) => {
              const x1 = timeToX(interval.start);
              const x2 = timeToX(interval.end);
              const width = Math.max(6, x2 - x1);
              const isWork = interval.type === 'work';

              return (
                <rect
                  key={`interval-${idx}`}
                  x={x1}
                  y={105}
                  width={width}
                  height={22}
                  rx={3}
                  fill={isWork ? '#065f46' : '#92400e'}
                  stroke={isWork ? '#10b981' : '#f59e0b'}
                  strokeWidth={1}
                  strokeDasharray={isWork ? 'none' : '3 2'}
                  opacity={inPunch && idx === intervals.length - 1 ? 0.75 : 1}
                />
              );
            });
          })()}

          {/* INDIVIDUAL PUNCH MARKERS */}
          {dayPunches.map((punch) => {
            const x = timeToX(punch.at);
            const isHighlighted = highlightedEvidenceId === punch.id;
            const isOut = punch.type === 'OUT';
            const isIn = punch.type === 'IN';

            const color = isIn ? '#10b981' : isOut ? '#38bdf8' : '#f59e0b';

            return (
              <g
                key={punch.id}
                data-testid={`punch-${punch.id}`}
                className="cursor-pointer"
                onClick={() => onSelectEvidence && onSelectEvidence(punch.id)}
                onMouseEnter={() =>
                  setHoveredItem({
                    label: `${punch.type} at ${new Date(punch.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} (${punch.id})`,
                    x,
                    y: 95,
                  })
                }
                onMouseLeave={() => setHoveredItem(null)}
              >
                {/* Highlight Halo if selected */}
                {isHighlighted && (
                  <circle cx={x} cy={116} r={14} fill="#818cf8" fillOpacity={0.4} stroke="#c7d2fe" strokeWidth={2} />
                )}

                {/* Marker Circle */}
                <circle
                  cx={x}
                  cy={116}
                  r={isHighlighted ? 8 : 6}
                  fill={color}
                  stroke="#ffffff"
                  strokeWidth={1.5}
                />

                {/* Marker Label */}
                <text x={x} y={138} fill="#e2e8f0" fontSize="8" fontWeight="600" textAnchor="middle">
                  {punch.type === 'IN'
                    ? 'IN'
                    : punch.type === 'OUT'
                    ? 'OUT'
                    : punch.type === 'BREAK_START'
                    ? 'B-START'
                    : 'B-END'}
                </text>
              </g>
            );
          })}

          {/* MISSED PUNCH BEACON (Visible at a glance!) */}
          {exceptionType === 'MISSED_PUNCH' && !hasOutPunch && primaryShift && (
            <g data-testid="missed-punch-beacon">
              {(() => {
                const shiftEndX = timeToX(primaryShift.end);
                return (
                  <>
                    {/* Pulsing indicator circle */}
                    <circle cx={shiftEndX} cy={116} r={15} fill="#f43f5e" fillOpacity={0.25} stroke="#f43f5e" strokeWidth={1.5} strokeDasharray="3 3" />
                    <circle cx={shiftEndX} cy={116} r={6} fill="#e11d48" stroke="#ffffff" strokeWidth={1.5} />

                    {/* Warning Callout Pin */}
                    <path
                      d={`M ${shiftEndX} 106 L ${shiftEndX - 5} 90 L ${shiftEndX + 5} 90 Z`}
                      fill="#e11d48"
                    />
                    <rect x={shiftEndX - 55} y={68} width={110} height={22} rx={4} fill="#e11d48" stroke="#fecdd3" strokeWidth={1} />
                    <text x={shiftEndX} y={82} fill="#ffffff" fontSize="8.5" fontWeight="bold" textAnchor="middle">
                      MISSING OUT PUNCH
                    </text>
                  </>
                );
              })()}
            </g>
          )}

          {/* PROPOSED PUNCH CHANGES (e.g. proposed add_punch at 17:00) */}
          {proposedChanges.map((change, idx) => {
            if (change.op === 'add_punch' && change.at) {
              const x = timeToX(change.at);
              return (
                <g key={`proposed-add-${idx}`} data-testid="proposed-punch-beacon">
                  <circle cx={x} cy={116} r={12} fill="#10b981" fillOpacity={0.3} stroke="#34d399" strokeWidth={2} strokeDasharray="2 2" />
                  <circle cx={x} cy={116} r={6} fill="#059669" stroke="#ffffff" strokeWidth={1.5} />
                  <rect x={x - 45} y={145} width={90} height={18} rx={3} fill="#065f46" stroke="#34d399" strokeWidth={1} />
                  <text x={x} y={157} fill="#a7f3d0" fontSize="8" fontWeight="bold" textAnchor="middle">
                    + PROPOSED {change.type}
                  </text>
                </g>
              );
            }
            return null;
          })}

          {/* Interactive Tooltip */}
          {hoveredItem && (
            <g pointerEvents="none">
              <rect
                x={hoveredItem.x - 70}
                y={hoveredItem.y - 25}
                width={140}
                height={20}
                rx={4}
                fill="#0f172a"
                stroke="#64748b"
                strokeWidth={1}
              />
              <text
                x={hoveredItem.x}
                y={hoveredItem.y - 12}
                fill="#f8fafc"
                fontSize="9"
                fontWeight="500"
                textAnchor="middle"
              >
                {hoveredItem.label}
              </text>
            </g>
          )}
        </svg>
      </div>
    </div>
  );
};
