import React from 'react';
import { memo, useCallback } from 'react';
import { useSelector, useDispatch } from 'react-redux';

import { COMMIT_MANAGER_URL } from 'constants/Layout';
import * as IconTypes from 'constants/Icons';

import NodePane from './NodePane';
import InlineBtn from '../../common/buttons/InlineBtn';

import { getOpenService, serviceToggled } from '../menuSlice';

import { stopThenGoToUrl } from 'api/comet';
import { useActionMutation, useGetValueQuery } from 'api/data';


const ServicePane = memo(function ServicePane(
  { keypath, children, topology, label, ...rest })
{
  console.debug('ServicePane Render');

  const { data } = useGetValueQuery(`${keypath}/modified/devices`);

  const isOpen = useSelector((state) => getOpenService(state) === keypath);
  const fade = useSelector((state) => !!getOpenService(state));

  const dispatch = useDispatch();
  const toggled = useCallback((keypath) => dispatch(serviceToggled({ keypath, highlightedIcons: isOpen ? [] : data })));

  const [ action ] = useActionMutation();
  const redeploy = useCallback(async (event) => {
    event.stopPropagation();
    await action({
      transType: 'read_write',
      path: `${keypath}/touch`
    });
    dispatch(stopThenGoToUrl(COMMIT_MANAGER_URL));
  });

  return (
    <NodePane
      keypath={keypath}
      label={label}
      isOpen={isOpen}
      fade={fade}
      nodeToggled={toggled}
      extraButtons={
        <InlineBtn
          type={IconTypes.BTN_REDEPLOY}
          classSuffix="redeploy"
          tooltip={`Redeploy (Touch) ${label}`}
          onClick={redeploy}
        />
      }
      {...rest}
    >
      {children}
    </NodePane>
  );
});

export default ServicePane;
