import React from 'react';
import { statusMeta } from './status';
export const StatusChipNative = ({ status, label, size = 'md', style, }) => {
    const meta = statusMeta[status] || statusMeta.pending;
    const displayText = label || meta.label;
    // Dynamically resolve React Native primitives if present, otherwise fallback to web elements
    let ViewComponent = 'div';
    let TextComponent = 'span';
    try {
        const rnModule = 'react-native';
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const RN = typeof require !== 'undefined' ? require(rnModule) : null;
        if (RN && RN.View && RN.Text) {
            ViewComponent = RN.View;
            TextComponent = RN.Text;
        }
    }
    catch (_e) {
        // In web environment
    }
    const isSm = size === 'sm';
    const containerStyle = {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: isSm ? 2 : 5,
        paddingHorizontal: isSm ? 8 : 12,
        borderRadius: 9999,
        borderWidth: 1,
        borderColor: meta.borderColor,
        backgroundColor: meta.backgroundColor,
        alignSelf: 'flex-start',
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
        fontWeight: '600',
    };
    return React.createElement(ViewComponent, { style: containerStyle }, React.createElement(ViewComponent, { style: dotStyle }), React.createElement(TextComponent, { style: textStyle }, displayText));
};
//# sourceMappingURL=StatusChipNative.js.map