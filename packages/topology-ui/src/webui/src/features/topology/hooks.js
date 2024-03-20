import { useContext, useCallback } from 'react';
import { useSelector } from 'react-redux';

import { CONFIGURATION_EDITOR_ACTIONS_URL } from 'constants/Layout';

import { getExpandedIcons,
         getVisibleUnderlays, getZoomedContainer } from './topologySlice';
import { getOpenTopologyName, getOpenTopology } from '../menu/menuSlice';

import { LayoutContext } from './LayoutContext';

import { stopThenGoToUrl } from 'api/comet';
import { setValue } from 'api/data';


const roundPc = (n) =>
  +Number.parseFloat(n).toFixed(2);

function isHidden(
  { hypervisor, iconUnderlay }, zoomedContainer, visibleUnderlays
) {
  const zoomed = zoomedContainer === hypervisor;
  return zoomedContainer && !zoomed ||
    iconUnderlay === 'true' && !visibleUnderlays.includes(hypervisor);
}

function calculateIconPosition(device, zoomed, container, dimensions) {
  const zoomedCoord = zoomed && {
    x: device.iconZoomedCoordX,
    y: device.iconZoomedCoordY
  };

  const { pc: { left, top, width, height }, connectionColour } = container;

  const pcX = roundPc(left + (zoomedCoord?.x || device.iconCoordX) * width);
  const pcY = roundPc(top + (zoomedCoord?.y || device.iconCoordY) * height);

  return {
    x: Math.round(pcX * dimensions.width / 100),
    y: Math.round(pcY * dimensions.height / 100),
    pcX, pcY, connectionColour
  };
}


export function useIconPosition(device) {
  const { containers, dimensions } = useContext(LayoutContext);
  const { hypervisor } = device;

  const zoomed = useSelector(state => getZoomedContainer(state) === hypervisor);
  const hidden = useSelector(state =>
    isHidden(device, getZoomedContainer(state), getVisibleUnderlays(state))
  );

  return !containers ? {} : {
    ...calculateIconPosition(device, zoomed, containers[hypervisor], dimensions),
    zoomed, hidden
  };
}

export function useIconPositionCalculator() {
  console.debug(`Reselect iconPositionCalculator`);
  const { containers, dimensions } = useContext(LayoutContext);
  const visibleUnderlays = useSelector((state) => getVisibleUnderlays(state));
  const zoomedContainer = useSelector((state) => getZoomedContainer(state));

  return useCallback(device => {
    if (!device) {
      return {};
    }

    const { hypervisor } = device;
    const zoomed = zoomedContainer === hypervisor;
    return {
      ...calculateIconPosition(device, zoomed, containers[hypervisor], dimensions),
      zoomed, hidden: isHidden(device, zoomedContainer, visibleUnderlays)
    };
  }, [ containers, visibleUnderlays, zoomedContainer ]);
}

export function useIsExpanded(name) {
  return useSelector((state) => getExpandedIcons(state)?.includes(name));
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
