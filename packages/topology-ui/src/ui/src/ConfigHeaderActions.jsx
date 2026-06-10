import React, { Fragment } from 'react';
import { useDispatch } from 'react-redux';

import InlineBtn from 'features/common/buttons/InlineBtn';
import * as IconTypes from 'constants/Icons';
import { libvirtAction } from './sidebar-modules/Topology';

function ConfigHeaderActions({ device }) {
  const dispatch = useDispatch();
  const onClick = (action) => (event) => {
    event.stopPropagation();
    dispatch(libvirtAction(action, device));
  };

  return (
    <Fragment>
      <InlineBtn
        icon={IconTypes.BTN_DEFINE}
        tooltip={'Define domain on KVM'}
        onClick={onClick('define')}
      />
      <InlineBtn
        icon={IconTypes.BTN_START}
        tooltip={'Start domain on KVM'}
        onClick={onClick('start')}
      />
      <InlineBtn
        icon={IconTypes.BTN_STOP}
        tooltip={'Stop domain on KVM'}
        onClick={onClick('stop')}
      />
      <InlineBtn
        icon={IconTypes.BTN_UNDEFINE}
        tooltip={'Undefine domain on KVM'}
        onClick={onClick('undefine')}
      />
      <InlineBtn
        icon={IconTypes.BTN_RESTART}
        tooltip={'Reboot domain on KVM'}
        onClick={onClick('reboot')}
      />
      <InlineBtn
        icon={IconTypes.BTN_RESET}
        style="danger"
        tooltip={'Hard reset domain on KVM (undefine and restart)'}
        onClick={onClick('hard-reset')}
      />
    </Fragment>
  );
}

export default ConfigHeaderActions;
