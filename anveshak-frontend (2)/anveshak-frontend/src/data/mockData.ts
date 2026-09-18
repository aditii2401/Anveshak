export interface MockCase {
  id: string;
  title: string;
  firNumber: string;
  policeStation: string;
  status: 'active' | 'pending' | 'closed';
  priority: 'high' | 'medium' | 'low';
  assignedOfficer: string;
  summary: string;
  dateCreated: string;
  riskScore: number;
  entitiesCount: number;
  leadsCount: number;
}

export interface MockActivity {
  id: string;
  action: string;
  timestamp: string;
  officer: string;
  caseId: string;
}

export interface MockNotification {
  id: string;
  title: string;
  message: string;
  time: string;
  unread: boolean;
  type: 'urgent' | 'info' | 'alert';
}

export const MOCK_CASES: MockCase[] = [
  {
    id: 'case-24-2026',
    title: 'Inter-State Hawala & Syndicate Liquidation',
    firNumber: 'FIR/2026/0102',
    policeStation: 'Crime Branch Unit 4, Nagpur',
    status: 'active',
    priority: 'high',
    assignedOfficer: 'Insp. R. Deshmukh',
    summary: 'Investigation into ₹18.4L cyclic transactions across multi-state mule accounts linked to Rathore Transport Services.',
    dateCreated: '2026-08-12',
    riskScore: 92,
    entitiesCount: 14,
    leadsCount: 6,
  },
  {
    id: 'case-18-2026',
    title: 'Illegal SIM Gateway & VOIP Routing',
    firNumber: 'FIR/2026/0078',
    policeStation: 'Cyber Cell, Pune',
    status: 'pending',
    priority: 'medium',
    assignedOfficer: 'Sub-Insp. A. Kadam',
    summary: 'Operation of 64 unauthorized GSM SIM boxes rerouting international traffic to domestic banking targets.',
    dateCreated: '2026-07-29',
    riskScore: 68,
    entitiesCount: 8,
    leadsCount: 3,
  },
  {
    id: 'case-09-2026',
    title: 'Vehicle Registration Forgery Ring',
    firNumber: 'FIR/2026/0034',
    policeStation: 'Traffic & RTO Special Cell, Raipur',
    status: 'closed',
    priority: 'low',
    assignedOfficer: 'Insp. V. Sharma',
    summary: 'Counterfeit smart-card RC certificates issued to inter-state commercial fleet operators.',
    dateCreated: '2026-05-14',
    riskScore: 35,
    entitiesCount: 5,
    leadsCount: 1,
  },
];

export const MOCK_NOTIFICATIONS: MockNotification[] = [
  {
    id: 'notif-1',
    title: 'High Correlation Alert',
    message: 'Bilateral call burst detected between Arjun Rathore and Vikram Patil (42 calls / 6 hours).',
    time: '12m ago',
    unread: true,
    type: 'urgent',
  },
  {
    id: 'notif-2',
    title: 'Financial Flag Triggered',
    message: 'Unusual ATM withdrawal of ₹6.2L in Raipur branch for account ...9981.',
    time: '45m ago',
    unread: true,
    type: 'alert',
  },
  {
    id: 'notif-3',
    title: 'Intelligence Ingest Complete',
    message: 'CDR records for 3 suspect MSISDNs have been cross-indexed successfully.',
    time: '2h ago',
    unread: false,
    type: 'info',
  },
];

export const MOCK_ACTIVITIES: MockActivity[] = [
  {
    id: 'act-1',
    action: 'Audited cash vouchers for Raipur SBI branch',
    timestamp: '10:45 AM',
    officer: 'Insp. R. Deshmukh',
    caseId: 'case-24-2026',
  },
  {
    id: 'act-2',
    action: 'Generated neural link dossier for Arjun Rathore',
    timestamp: '09:30 AM',
    officer: 'Cyber Intelligence Node',
    caseId: 'case-24-2026',
  },
  {
    id: 'act-3',
    action: 'Attached FIR 102/2026 certified extract',
    timestamp: 'Yesterday',
    officer: 'Sub-Insp. A. Kadam',
    caseId: 'case-24-2026',
  },
];

export const MOCK_BANKING_RECORDS = [
  {
    txnId: 'TXN_44S1_01',
    fromAccount: 'Arjun Rathore (Axis ...4129)',
    toAccount: 'Vikram Patil (SBI ...9981)',
    amount: '₹4,50,000',
    date: '2026-08-14 11:22',
    mode: 'RTGS',
    status: 'Flagged (Cyclic)',
  },
  {
    txnId: 'TXN_44S1_02',
    fromAccount: 'Vikram Patil (SBI ...9981)',
    toAccount: 'Rathore Transport Services (HDFC ...1022)',
    amount: '₹4,20,000',
    date: '2026-08-15 09:14',
    mode: 'NEFT',
    status: 'Flagged (Pass-through)',
  },
  {
    txnId: 'TXN_44S1_03',
    fromAccount: 'Rathore Transport (HDFC ...1022)',
    toAccount: 'Cash Withdrawal (Raipur Branch)',
    amount: '₹6,20,000',
    date: '2026-08-15 14:05',
    mode: 'Counter Cash Voucher',
    status: 'High Alert (Liquidation)',
  },
];