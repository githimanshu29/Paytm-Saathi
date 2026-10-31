import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { statusMeta } from './status';
export const StatusChip = ({ status, label, size = 'md', className = '', style = {}, }) => {
    const meta = statusMeta[status] || statusMeta.pending;
    const displayText = label || meta.label;
    const sizeStyles = size === 'sm'
        ? {
            padding: '2px 8px',
            fontSize: '11px',
            borderRadius: '9999px',
        }
        : {
            padding: '4px 12px',
            fontSize: '13px',
            borderRadius: '9999px',
        };
    const chipStyle = {
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        fontWeight: 600,
        lineHeight: 1.2,
        borderWidth: '1px',
        borderStyle: 'solid',
        borderColor: meta.borderColor,
        backgroundColor: meta.backgroundColor,
        color: meta.textColor,
        fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        transition: 'all 0.15s ease-in-out',
        ...sizeStyles,
        ...style,
    };
    const dotStyle = {
        width: size === 'sm' ? '6px' : '7px',
        height: size === 'sm' ? '6px' : '7px',
        borderRadius: '50%',
        backgroundColor: meta.textColor,
    };
    return (_jsxs("span", { style: chipStyle, className: `saathi-status-chip saathi-status-chip--${status} ${className}`, children: [_jsx("span", { style: dotStyle }), _jsx("span", { children: displayText })] }));
};
//# sourceMappingURL=StatusChip.js.map