import React from 'react';
import { StatusType, statusMeta } from './status';

declare const require: any;

export interface StatusChipNativeProps {
  status: StatusType;
  label?: string;
  size?: 'sm' | 'md';
  style?: any;
}

export const StatusChipNative: React.FC<StatusChipNativeProps> = ({
  status,
  label,
  size = 'md',
  style,
}) => {
  const meta = statusMeta[status] || statusMeta.pending;
  const displayText = label || meta.label;

  // Dynamically resolve React Native primitives if present, otherwise fallback to web elements
  let ViewComponent: any = 'div';
  let TextComponent: any = 'span';
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const RN = require('react-native');
    if (RN && RN.View && RN.Text) {
      ViewComponent = RN.View;
      TextComponent = RN.Text;
    }
  } catch (_e) {
    // In web environment
  }

  const isSm = size === 'sm';

  const containerStyle = {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    paddingVertical: isSm ? 2 : 5,
    paddingHorizontal: isSm ? 8 : 12,
    borderRadius: 9999,
    borderWidth: 1,
    borderColor: meta.borderColor,
    backgroundColor: meta.backgroundColor,
    alignSelf: 'flex-start' as const,
    ...(style || {}),
  };

  const dotStyle = {
    width: isSm ? 6 : 7,
    height: isSm ? 6 : 7,
    borderRadius: 4,
    backgroundColor: meta.textColor,
    marginRight: 6,
  };

  const textStyle = {
    color: meta.textColor,
    fontSize: isSm ? 11 : 13,
    fontWeight: '600' as const,
  };

  return React.createElement(
    ViewComponent,
    { style: containerStyle },
    React.createElement(ViewComponent, { style: dotStyle }),
    React.createElement(TextComponent, { style: textStyle }, displayText)
  );
};
