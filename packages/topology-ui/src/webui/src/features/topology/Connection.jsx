import React from 'react';
import { memo,
         useRef, useContext, useEffect, useCallback, useMemo } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import classNames from 'classnames';

import { BTN_DRAG, BTN_DELETE } from 'constants/Icons';
import { CIRCLE_ICON_RATIO, LINE_ICON_RATIO } from 'constants/Layout.js';

import Interface from './Interface';
import RoundButton from './RoundButton';

import { getDraggedItem, getSelectedConnection, getEditMode,
         connectionSelected } from './topologySlice';

import { useIconPosition, useIsExpanded, useOpenTopologyName } from './hooks';

import { LayoutContext } from './LayoutContext';
import { useDevice } from './Icon';

import { useQueryQuery, createItemsSelector } from 'api/query';
import { useDeletePathMutation } from 'api/data';


// === Queries ================================================================

export function useConnectionsQuery() {
  const topology = useOpenTopologyName();
  return useQueryQuery({
    xpathExpr: '/topology:topologies/topology/links/link',
    selection: [ '../../name', 'a-end-device', 'z-end-device' ]
  }, { selectFromResult: useMemo(() =>
    createItemsSelector('parentName', topology), [ topology ])
  });
}


// === Utils ==================================================================

export function pointAlongLine(x1, y1, x2, y2, n) {
  const d = lineLength({ x1, y1, x2, y2 });
  if (d > n) {
    const r = n / d;
    const x = r * x2 + (1 - r) * x1;
    const y = r * y2 + (1 - r) * y1;
    return { x, y };
  } else {
    return { x: x2, y: y2 };
  }
}

function lineLength({ x1, y1, x2, y2 }) {
  return Math.sqrt((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1));
}

function lineAngle({ x1, y1, x2, y2 }) {
  const theta = Math.atan2(y2 - y1, x2 - x1);
  const angle = theta * 180 / Math.PI;
  if (angle < 0) {
    return angle + 360;
  } else {
    return angle;
  }
}


// === Component ==============================================================

const Connection = memo(function Connection({ keypath, aEndDevice, zEndDevice }) {
  console.debug('Connection Render');

  const dispatch = useDispatch();
  const [ deletePath ] = useDeletePathMutation();

  const layout = useContext(LayoutContext);

  const editMode = useSelector((state) => getEditMode(state));
  const dragging = useSelector((state) => {
    const draggedItem = getDraggedItem(state);
    return !!draggedItem &&
      (aEndDevice == (draggedItem.aEndDevice || draggedItem.fromDevice) &&
       zEndDevice == (draggedItem.zEndDevice || draggedItem.fromDevice) ||
       draggedItem.icon === aEndDevice ||
        draggedItem.icon === zEndDevice);
  });
  const selected = useSelector((state) => {
    const selectedConnection = getSelectedConnection(state);
    return Boolean(editMode && selectedConnection
      && selectedConnection.aEndDevice === aEndDevice
      && selectedConnection.zEndDevice === zEndDevice);
  });

  const connSelected = () => {
    editMode && dispatch(connectionSelected({ aEndDevice, zEndDevice }));
  };

  const deleteConn = useCallback(() => {
    dispatch(deletePath({ keypath }));
  }, []);

  const { x: x1, y: y1, ...aEndIcon } = useIconPosition(useDevice(aEndDevice));
  const { x: x2, y: y2, ...zEndIcon } = useIconPosition(useDevice(zEndDevice));
  const expanded = useIsExpanded(aEndDevice) | useIsExpanded(zEndDevice);
  const hidden = aEndIcon.hidden || zEndIcon.hidden;
  const colour = aEndIcon.connectionColour || zEndIcon.connectionColour;
  const { iconSize, dimensions } = layout;
  const iconRadius = iconSize / 2;
  const circleSize = iconSize * CIRCLE_ICON_RATIO;
  const lineWidth = iconSize * LINE_ICON_RATIO;
  const p1 = pointAlongLine(x1, y1, x2, y2, iconRadius);
  const p2 = pointAlongLine(x2, y2, x1, y1, iconRadius);
  const line = { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y };
  const length = lineLength(line);
  const p3 = pointAlongLine(p1.x, p1.y, p2.x, p2.y, length / 2);
  const pcP1 = layout.pxToPc(p1);

  const lineAngleRef = useRef(0);
  let actualLineAngle = lineAngleRef.current;

  if (length > 0) {
    actualLineAngle = lineAngle(line);
    // Always apply the shortest rotation
    if ((lineAngleRef.current - actualLineAngle) > 180) {
      actualLineAngle += 360;
    } else if ((lineAngleRef.current - actualLineAngle) < -180) {
      actualLineAngle -= 360;
    }
  }
  useEffect(() => {
    lineAngleRef.current = actualLineAngle;
  }, [ x1, y1, x2, y2 ]);

  return (
    <div
      id={`${aEndDevice} - ${zEndDevice}`}
      onClick={connSelected}
      className={classNames('topology__connection', {
        'topology__connection--selected': selected || expanded,
        'topology__connection--edit': editMode,
        'topology__connection--dragging': dragging,
        'topology__connection--hidden': hidden
      })}
      style={{
        background: !selected && !expanded ? colour : null,
        height: `${lineWidth}px`,
        left: `${pcP1.pcX}%`,
        top: `${pcP1.pcY}%`,
        transform: `rotate(${actualLineAngle}deg) translate(0, -50%)`,
        width: `${length / dimensions.width * 100}%`
      }}
    >
      <Interface
        keypath={keypath}
        aEndDevice={aEndDevice}
        fromDevice={zEndDevice}
        pcX="0"
        pcY="50"
        {...p1}
        size={circleSize}
        active={selected}
        type={BTN_DRAG}
        tooltip="Move Connection (drag me)"
      />
      <Interface
        keypath={keypath}
        zEndDevice={zEndDevice}
        fromDevice={aEndDevice}
        pcX="100"
        pcY="50"
        {...p2}
        size={circleSize}
        active={selected}
        type={BTN_DRAG}
        tooltip="Move Connection (drag me)"
      />
      <RoundButton
        onClick={deleteConn}
        pcX="50"
        pcY="50"
        {...p3}
        hide={!selected}
        size={circleSize}
        active={selected}
        type={BTN_DELETE}
        tooltip="Delete Connection"
      />
    </div>
  );
});

export default Connection;
