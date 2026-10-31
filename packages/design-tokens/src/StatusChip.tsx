import React from 'react';
import { StatusType, statusMeta } from './status';

export interface StatusChipProps {
  status: StatusType;
  label?: string;
  size?: 'sm' | 'md';
  className?: string;
  style?: React.CSSProperties;
}

export const StatusChip: React.FC<StatusChipProps> = ({
  status,
  label,
  size = 'md',
  className = '',
  style = {},
}) => {
  const meta = statusMeta[status] || statusMeta.pending;
  const displayText = label || meta.label;

  const sizeStyles: React.CSSProperties =
    size === 'sm'
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

  const chipStyle: React.CSSProperties = {
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

  const dotStyle: React.CSSProperties = {
    width: size === 'sm' ? '6px' : '7px',
    height: size === 'sm' ? '6px' : '7px',
    borderRadius: '50%',
    backgroundColor: meta.textColor,
  };

  return (
    <span style={chipStyle} className={`saathi-status-chip saathi-status-chip--${status} ${className}`}>
      <span style={dotStyle} />
      <span>{displayText}</span>
    </span>
  );
};
