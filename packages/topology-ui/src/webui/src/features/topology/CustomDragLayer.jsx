import React from 'react';
import { useSelector } from 'react-redux';

import DragLayerDrawer from './DragLayerDrawer';

import { useDevicesQuery, useDevice } from './Icon';
import { getDraggedItem, getHoveredIcon } from './topologySlice';
import { useIconPositionCalculator, useConnectedDevices } from './hooks';


function CustomDragLayer({ canvasRef }) {
  console.debug('CustomDragLayer Render');

  const { data } = useDevicesQuery();
  const iconPosition = useIconPositionCalculator();
  const { icon, fromDevice } = useSelector((state) => getDraggedItem(state)) || {};
  const connectedDevices = useConnectedDevices(icon);
  const hoveredIcon = useDevice(useSelector((state) => getHoveredIcon(state)));

  const fromDevices = data ? data.filter(({ name, parentName }) => (fromDevice
    ? fromDevice === name : icon && connectedDevices.includes(name))) : [];

  return (
    <DragLayerDrawer
      canvasRef={canvasRef}
      fromIcons={fromDevices.map(device => iconPosition(device))}
      toIcon={hoveredIcon && iconPosition(hoveredIcon)}
    />
  );
}

export default CustomDragLayer;
