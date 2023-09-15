import React from 'react';

export default React.forwardRef(({size}, ref) =>
  <svg
    ref={ref}
    className="round-btn__svg-icon"
    style={{height: `${size}px`, width: `${size}px`}}
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 512 512"
  >
    <path
      fill="currentColor"
      d="M497.913,429.906l-84.863-84.848c22.365-34.903,35.718-76.146,35.718-120.676C448.768,100.453,348.314,0,224.383,0    C100.468,0,0,100.453,0,224.384s100.468,224.384,224.383,224.384c44.529,0,85.771-13.352,120.66-35.718l84.862,84.864    c18.782,18.781,49.226,18.781,68.008,0C516.695,479.131,516.695,448.689,497.913,429.906z M224.383,384.658    c-88.511,0-160.274-71.748-160.274-160.274c0-88.511,71.764-160.274,160.274-160.274c88.526,0,160.273,71.763,160.273,160.274    C384.656,312.91,312.909,384.658,224.383,384.658z M128.219,256.438h192.329v-64.109H128.219V256.438z"
    />
  </svg>
);
