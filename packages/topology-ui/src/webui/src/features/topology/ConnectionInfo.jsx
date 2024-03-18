import React from 'react';
import { forwardRef } from 'react';

const ConnectionInfo = forwardRef(function ConnectionInfo(props, ref) {
  const { actualLineAngle, hide, igp, te, delay } = props;
  const spacing_em = 1.625;
  const angle = 360-actualLineAngle;

  const data = {};
  if (igp) { data['I'] = igp; }
  if (te) { data['T'] = te; }
  if (delay) { data['D'] = delay; }
  const keys = Object.keys(data);
  const offset = (keys.length - 1)/2 * spacing_em;

  return (
    !hide ? <React.Fragment>
      {keys.map((key, index) =>
      <div className="topology__connection-info" key={key} style={{
        transform: `rotate(${angle}deg) translate(0, ${index*spacing_em - offset}em)`
      }}>
        <div className="topology__metric">{key}</div>
        <div className="topology__metric-value">{data[key]}</div>
      </div>)}
    </React.Fragment>
  : null);
});

export default ConnectionInfo;
