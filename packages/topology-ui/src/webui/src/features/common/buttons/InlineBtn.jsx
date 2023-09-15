import React from 'react';
import { Fragment, forwardRef } from 'react';
import classNames from 'classnames';
import Tippy from '@tippyjs/react';

import { BTN_CONFIRM } from 'constants/Icons';
import Btn from './BtnWithTooltip';

const InlineBtn = forwardRef(
  function InlineBtn({ type, classSuffix, tooltip, onClick, label, align }, ref)
{
  return (
    <Tippy placement="bottom" content={tooltip}>
      <button
        className={classNames(
          'btn__inline', {
            'btn__round': !label,
            'btn__inline--with-label': label,
            [ `btn--${classSuffix}` ]: classSuffix,
            [ `btn__inline--${align}-align` ]: align
          }
        )}
        ref={ref}
        onClick={onClick}
        type={type === BTN_CONFIRM ? 'submit' : 'button'}
      >{label ?
        <Fragment>{type &&
          <div className="btn__round" >
            <Btn type={type} />
          </div>}
          <span className="btn__text">{label}</span>
        </Fragment> :
        <Btn type={type} />}
      </button>
    </Tippy>
  );
});

export default InlineBtn;
