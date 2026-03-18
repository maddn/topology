import React from 'react';
import { useCallback } from 'react';
import { useSelector, useDispatch } from 'react-redux';

import NodePane from '../panels/NodePane';
import InlineBtn from '../../common/buttons/InlineBtn';
import * as ManagedTopology from './ManagedTopology';
import * as IpConnectivity from './IpConnectivity';
import * as BaseConfig from './BaseConfig';

import { CONFIGURATION_EDITOR_ACTIONS_URL } from 'constants/Layout';
import * as IconTypes from 'constants/Icons';

import { useQueryQuery, useQueryState, useMemoizeWhenFetched, swapLabels,
         selectItem } from 'api/query';
import { stopThenGoToUrl } from 'api/comet';
import { setValue } from 'api/data';

import { topologyToggled,
         getOpenTopology, getOpenTopologyName } from '../menuSlice';

export const label = 'Topology';
export const path = '/topology:topologies/topology';

const selection = {
  'provisioning-status': 'Provisioning Status'
};

export function useQuery(itemSelector) {
  return useQueryQuery({
    xpathExpr: path,
    selection:  [ 'name', ...Object.keys(selection) ],
  }, { selectFromResult: itemSelector });
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'Topologies Connectivity Services': useQueryState(path),
    ...IpConnectivity.useFetchStatus(),
    ...BaseConfig.useFetchStatus()
  });
}

export function useOpenTopologyName() {
  return useSelector((state) => getOpenTopologyName(state));
}

export const libvirtAction = (action, device) => async (dispatch, getState) => {
  const openTopology = getOpenTopology(getState());
  const actionPath = `${openTopology}/libvirt/${action}`;
  await dispatch(setValue.initiate({
    actionPath, leaf: 'device', value: device}));
  dispatch(stopThenGoToUrl(`${CONFIGURATION_EDITOR_ACTIONS_URL}${actionPath}`));
};


export const Component = React.memo(function Component({ name }) {
  console.debug('Topologies Render');

  const dispatch = useDispatch();
  const { data } = useQuery(selectItem('name', name));
  const { keypath } = data;

  const goToLibvirtAction = (event, action) => {
    event.stopPropagation();
    dispatch(libvirtAction(action, null));
  };

  return (
    <NodePane
      key={name}
      title={name}
      label={label}
      level="0"
      isOpen={useSelector((state) => getOpenTopology(state) === keypath)}
      fade={useSelector((state) => !!getOpenTopology(state))}
      nodeToggled={useCallback((keypath) => dispatch(topologyToggled(keypath)))}
      keypath={keypath}
      subHeader={
        <div className="config-viewer__btn-row">
          <InlineBtn
            icon={IconTypes.BTN_DEFINE}
            tooltip="Define domain on KVM"
            onClick={(event) => goToLibvirtAction(event, 'define')}
            label="Define"
          />
          <InlineBtn
            icon={IconTypes.BTN_START}
            tooltip="Start domain on KVM"
            onClick={(event) => goToLibvirtAction(event, 'start')}
            label="Start"
          />
          <InlineBtn
            icon={IconTypes.BTN_STOP}
            style="danger"
            tooltip={'Stop domain on KVM'}
            onClick={(event) => goToLibvirtAction(event, 'stop')}
            label="Stop"
          />
          <InlineBtn
            icon={IconTypes.BTN_UNDEFINE}
            style="danger"
            tooltip={'Undefine domain on KVM'}
            onClick={(event) => goToLibvirtAction(event, 'undefine')}
            label="Undefine"
          />
        </div>
      }
        { ...swapLabels(data, selection) }
    >
      <ManagedTopology.Component name={name}/>
      <IpConnectivity.Component topology={name}/>
      <BaseConfig.Component topology={name}/>
    </NodePane>
  );
});
