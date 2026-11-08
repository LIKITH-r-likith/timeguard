import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DayTimeline } from '../DayTimeline';
import type { Shift, Punch, TimecardChange } from '../../types';

describe('DayTimeline Component', () => {
  const mockShifts: Shift[] = [
    {
      id: 's_01',
      employee_id: 'e01',
      start: '2026-11-03T09:00:00+05:30',
      end: '2026-11-03T17:00:00+05:30',
      scheduled_break_minutes: 30,
    },
  ];

  const mockPunches: Punch[] = [
    {
      id: 'p_01',
      employee_id: 'e01',
      type: 'IN',
      at: '2026-11-03T09:00:00+05:30',
    },
    {
      id: 'p_02',
      employee_id: 'e01',
      type: 'BREAK_START',
      at: '2026-11-03T13:00:00+05:30',
    },
    {
      id: 'p_03',
      employee_id: 'e01',
      type: 'BREAK_END',
      at: '2026-11-03T13:30:00+05:30',
    },
  ];

  it('renders SVG timeline with grid and work date', () => {
    render(
      <DayTimeline
        workDate="2026-11-03"
        shifts={mockShifts}
        punches={mockPunches}
      />
    );

    const svg = screen.getByTestId('day-timeline-svg');
    expect(svg).toBeInTheDocument();
    expect(screen.getByText('2026-11-03')).toBeInTheDocument();
  });

  it('renders scheduled shift rectangle and overtime zone', () => {
    render(
      <DayTimeline
        workDate="2026-11-03"
        shifts={mockShifts}
        punches={mockPunches}
      />
    );

    expect(screen.getByTestId('shift-s_01')).toBeInTheDocument();
    expect(screen.getByTestId('overtime-zone')).toBeInTheDocument();
  });

  it('renders punches including IN and BREAK punches', () => {
    render(
      <DayTimeline
        workDate="2026-11-03"
        shifts={mockShifts}
        punches={mockPunches}
      />
    );

    expect(screen.getByTestId('punch-p_01')).toBeInTheDocument();
    expect(screen.getByTestId('punch-p_02')).toBeInTheDocument();
    expect(screen.getByTestId('punch-p_03')).toBeInTheDocument();
  });

  it('displays missed punch beacon when exception is MISSED_PUNCH and OUT punch is missing', () => {
    render(
      <DayTimeline
        workDate="2026-11-03"
        shifts={mockShifts}
        punches={mockPunches}
        exceptionType="MISSED_PUNCH"
      />
    );

    expect(screen.getByTestId('missed-punch-beacon')).toBeInTheDocument();
    expect(screen.getByText('MISSING OUT PUNCH')).toBeInTheDocument();
  });

  it('displays proposed punch beacon when proposed changes include an add_punch', () => {
    const proposedChanges: TimecardChange[] = [
      {
        op: 'add_punch',
        type: 'OUT',
        at: '2026-11-03T17:00:00+05:30',
      },
    ];

    render(
      <DayTimeline
        workDate="2026-11-03"
        shifts={mockShifts}
        punches={mockPunches}
        proposedChanges={proposedChanges}
      />
    );

    expect(screen.getByTestId('proposed-punch-beacon')).toBeInTheDocument();
    expect(screen.getByText('+ PROPOSED OUT')).toBeInTheDocument();
  });
});
