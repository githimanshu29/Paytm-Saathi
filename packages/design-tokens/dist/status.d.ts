export type StatusType = 'verified' | 'executed' | 'pending' | 'awaiting_approval' | 'needs_human';
export interface StatusMeta {
    key: StatusType;
    label: string;
    textColor: string;
    backgroundColor: string;
    borderColor: string;
}
export declare const statusMeta: Record<StatusType, StatusMeta>;
//# sourceMappingURL=status.d.ts.map