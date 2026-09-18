export type RiskLevel = 'high' | 'warning' | 'medium' | 'low';

export interface Entity {
  id: string;
  name: string;
  type: 'person' | 'account' | 'vehicle' | 'phone' | 'case';
  role: string;
  riskLevel: RiskLevel;
  identifier?: string;
  flaggedReasons?: string[];
  notes?: string;
  dataSources?: string[];
}