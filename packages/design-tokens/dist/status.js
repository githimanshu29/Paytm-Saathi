import { colors } from './colors';
export const statusMeta = {
    verified: {
        key: 'verified',
        label: 'Verified',
        textColor: colors.chip.verified.text,
        backgroundColor: colors.chip.verified.bg,
        borderColor: colors.chip.verified.border,
    },
    executed: {
        key: 'executed',
        label: 'Executed',
        textColor: colors.chip.executed.text,
        backgroundColor: colors.chip.executed.bg,
        borderColor: colors.chip.executed.border,
    },
    pending: {
        key: 'pending',
        label: 'Pending',
        textColor: colors.chip.pending.text,
        backgroundColor: colors.chip.pending.bg,
        borderColor: colors.chip.pending.border,
    },
    awaiting_approval: {
        key: 'awaiting_approval',
        label: 'Awaiting Approval',
        textColor: colors.chip.awaiting_approval.text,
        backgroundColor: colors.chip.awaiting_approval.bg,
        borderColor: colors.chip.awaiting_approval.border,
    },
    needs_human: {
        key: 'needs_human',
        label: 'Needs Human',
        textColor: colors.chip.needs_human.text,
        backgroundColor: colors.chip.needs_human.bg,
        borderColor: colors.chip.needs_human.border,
    },
};
//# sourceMappingURL=status.js.map