import React from 'react';
import { Fragment, useCallback,
         useContext, useEffect, useMemo} from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { renderToStaticMarkup } from 'react-dom/server';
import { useDrop, useDrag } from 'react-dnd';
import { getEmptyImage } from 'react-dnd-html5-backend';
import classNames from 'classnames';
import Tippy from '@tippyjs/react';

import { ICON, INTERFACE, DEVICE } from 'constants/ItemTypes';
import { CIRCLE_ICON_RATIO, ICON_VNF_SPACING } from 'constants/Layout';
import { BTN_ADD } from 'constants/Icons';
import { HIGHLIGHT, HOVER } from 'constants/Colours';

import Interface from './Interface';
import IconHighlight from './icons/IconHighlight';
import IconSvg from './icons/IconSvg';

import { getSelectedIcon, getEditMode, getHighlightedIcons, getExpandedIcons,
         itemDragged, iconHovered, connectionSelected, iconSelected,
         getZoomedContainer, getVisibleUnderlays,
         iconExpandToggled } from './topologySlice';
import { getOpenTopology } from 'features/menu/menuSlice';
import { useOpenTopologyName } from 'features/menu/modules/Topology';

import { useConnectedDevices } from './Connection';

import { LayoutContext} from './LayoutContext';
import { isSafari, connectPngDragPreview } from './DragLayerCanvas';

import { selectItem, selectItemWithArray,
         createItemsSelector, useQueryQuery } from '/api/query';
import { useSetValueMutation,
         useCreateMutation, useDeletePathMutation } from '/api/data';



// === Queries ================================================================

function __useDevicesQuery(selectFromResult) {
  return useQueryQuery({
    xpathExpr: '/topology:topologies/topology/devices/device',
    selection: [
      'device-name',
      'id',
      '../../name',
      'definition',
      'provisioning-status',
      'operational-status',
      'hypervisor',
      'icon/type',
      'icon/coord/x',
      'icon/coord/y',
      'icon/zoomed/coord/x',
      'icon/zoomed/coord/y',
      'icon/underlay' ],
    subscribe: true
    }, { selectFromResult }
  );
}

export function useDevicesQuery() {
  const topology = useOpenTopologyName();
  return __useDevicesQuery(useMemo(() =>
    createItemsSelector('parentName', topology), [ topology ]));
}

export function useDevice(name) {
  const device = __useDevicesQuery(selectItemWithArray([
    [ 'parentName', useOpenTopologyName() ], [ 'name', name ]
  ])).data;
  if (name && !device) {
    console.error(`Device ${name} doesn't exist`);
  }
  return device;
}

export function usePlatformsQuery(itemSelector) {
  return useQueryQuery({
    xpathExpr: '/ncs:devices/device/platform',
    selection: [ '../name', 'name', 'model', 'version' ]
  }, { selectFromResult: itemSelector });
}

export function usePlatform(deviceName) {
  return usePlatformsQuery(selectItem('parentName', deviceName)).data;
}



// === Util functions =========================================================

function positionStyle(position, size) {
  return {
    left: `${position.pcX}%`,
    top: `${position.pcY}%`,
    transform: `translate(-50%, ${-size/2}px)`,
  };
}

export function svgStyle(size) {
  return {
    height: `${size}px`,
    width: `${size}px`,
  };
}

const roundPc = (n) =>
  +Number.parseFloat(n).toFixed(2);

function calculateIconPosition(
  device, zoomed, container, dimensions) {
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

function isHidden(
  { hypervisor, iconUnderlay }, zoomedContainer, visibleUnderlays
) {
  const zoomed = zoomedContainer === hypervisor;
  return zoomedContainer && !zoomed ||
    iconUnderlay === 'true' && !visibleUnderlays.includes(hypervisor);
}


// === Hooks ==================================================================

export function useIsExpanded(name) {
  return useSelector((state) => getExpandedIcons(state)?.includes(name));
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


// === Component ==============================================================

function Icon({ name }) {
  console.debug('Icon Render');
  const mouseDownPos = {};

  const dispatch = useDispatch();
  const [ setValue ] = useSetValueMutation();
  const [ create ] = useCreateMutation();
  const [ deletePath ] = useDeletePathMutation();

  const { iconSize: size, pxToPc } = useContext(LayoutContext);

  const platform = usePlatform(name);
  const device = useDevice(name);
  const { keypath, iconType, definition, provisioningStatus, operationalStatus } = device;
  const container = device.hypervisor;
  const status = provisioningStatus === 'ready'
    ? operationalStatus : provisioningStatus;

  const selected = useSelector((state) => getSelectedIcon(state) === name);
  const highlighted = useSelector(
    (state) => getHighlightedIcons(state)?.includes(name));
  const editMode = useSelector((state) => getEditMode(state));
  const openTopologyKeypath = useSelector((state) => getOpenTopology(state));

  const openTopology = useOpenTopologyName();
  const expanded = useIsExpanded(name);
  const connectedDevices = useConnectedDevices(name);
  const { x, y, pcX, pcY, zoomed, hidden } = useIconPosition(device);

  const [, deviceDrag, deviceDragPreview] = useDrag(() => ({
    type: DEVICE,
    item: { name, type: iconType },
    canDrag: !editMode
  }));

  const [ collectedDragProps, iconDrag, iconDragPreview ] = useDrag(() => ({
    type: ICON,
    item: () => {
      const img = new Image();
      img.src = `data:image/svg+xml,${encodeURIComponent(renderToStaticMarkup(
            <IconSvg type={iconType} status={status} size={size} />
      ))}`;
      const item = {
        icon: { name, img, imgReady: false, container}, x, y,  mouseDownPos
      };
      img.onload = () => { item.icon.imgReady = true; };
      requestAnimationFrame(
        () => { dispatch(itemDragged({ icon: name, container })); });
      return item;
    },
    end: (item, monitor) => {
      const offset = monitor.getDifferenceFromInitialOffset();
      dispatch(itemDragged(undefined));
      moveIcon(item.x + offset.x, item.y + offset.y);
    },
    canDrag: editMode,
    collect: (monitor) => ({ isDragging: monitor.isDragging() })
  }), [ mouseDownPos ]);

  const [ collectedDropProps, drop ] = useDrop(() => ({
    accept: INTERFACE,
    drop: (item) => {
      const { aEndDevice: aEnd, zEndDevice: zEnd,
              keypath, fromDevice } = item.interface;
      const aEndDevice = aEnd ? name : fromDevice;
      const zEndDevice = (zEnd || !aEnd) ? name : fromDevice;

      if (keypath) {
        deletePath({ keypath });
      }

      create({
        keypath: `${openTopologyKeypath}/links/link`,
        name: `${aEndDevice} ${zEndDevice}`,
        aEndDevice, zEndDevice,
        parentName: openTopology,
      });
      dispatch(connectionSelected({ aEndDevice, zEndDevice }));
    },
    canDrop: (item, monitor) => {
      const hoveredInterface = monitor.isOver() && item;
      if (!hoveredInterface) {
        return false;
      }
      const { fromDevice } = hoveredInterface.interface;
      if (name === fromDevice ) {
        return false;
      }
      return !connectedDevices.includes(fromDevice);
    },
    collect: (monitor) => ({
      canDrop: monitor.canDrop()
    })
  }), [ connectedDevices ]);

  const handleOnClick = () => {
    if (editMode && name ) {
      dispatch(iconSelected(name));
    } else if (!editMode) {
      dispatch(iconExpandToggled(name));
    }
  };

  const moveIcon = (x, y) => {
    const coordNode = `icon/${zoomed ? 'zoomed/' : ''}coord/`;
    const coordValue = pxToPc({ x, y }, container);
    setValue({ keypath, leaf: `${coordNode}x`, value: coordValue.x });
    setValue({ keypath, leaf: `${coordNode}y`, value: coordValue.y});
  };

  const handleMouseDown = event => {
    mouseDownPos.x = event.clientX;
    mouseDownPos.y = event.clientY;
  };

  const tooltipContent =
    <table className="tooltip">
      <tbody>
        <tr><td>Device:</td><td>{name}</td></tr>
        <tr><td>Definition:</td><td>{definition}</td></tr>
        <tr><td>Status:</td><td>{provisioningStatus}</td></tr>
        <tr><td>Oper:</td><td>{operationalStatus}</td></tr>
        {platform &&
          <Fragment>
            <tr><td>Platform:</td><td>{platform.name}</td></tr>
            <tr><td>Version:</td><td>{platform.version}</td></tr>
            <tr><td>Model:</td><td>{platform.model}</td></tr>
          </Fragment>
        }
      </tbody>
    </table>;

  const { canDrop } = collectedDropProps;

  useEffect(() => {
    dispatch(iconHovered(canDrop && name));
  }, [ canDrop ]);

  useEffect(() => {
    iconDragPreview(getEmptyImage(), {});
  });

  const { isDragging } = collectedDragProps;

  const position = { x, y, pcX, pcY };
  const outlineSize = expanded ? Math.round(size * ICON_VNF_SPACING) : size;
  const highlightSize = size * 2;

  // The drag preview is not captured correctly on Safari,
  // so generate PNG image and use that
  isSafari && connectPngDragPreview(renderToStaticMarkup(
    <IconSvg type={iconType} status={status} size={size} />),
    size, deviceDragPreview, false
  );

  return (
    <Fragment>
      <div
        onClick={handleOnClick}
        id={`${name}-outline`}
        className={classNames('icon__outline', {
          'icon__outline--expanded': expanded,
          'icon__container--hidden': hidden
        })}
        style={{
          ...positionStyle(position, outlineSize),
          ...svgStyle(outlineSize),
          borderRadius: `${outlineSize / 2}px`,
        }}
      >
      </div>
      <div
        className={classNames('icon__container', {
          'icon__container--hidden': !canDrop
        })}
        style={positionStyle(position, highlightSize)}
      >
        <IconHighlight size={highlightSize} colour={HOVER}/>
      </div>
      <div
        className={classNames('icon__container', {
          'icon__container--expanded': expanded,
          'icon__container--hidden': hidden || editMode || !highlighted
        })}
        style={positionStyle(position, highlightSize)}
      >
        <IconHighlight size={highlightSize} colour={HIGHLIGHT}/>
      </div>
      {deviceDragPreview(
        <div
          id={`${name}-icon`}
          className={classNames('icon__container', {
            'icon__container--expanded': expanded,
            'icon__container--dragging': isDragging,
            'icon__container--hidden': hidden
          })}
          style={positionStyle(position, size)}
        >
          <div
            className="icon__svg-wrapper icon__svg-wrapper--hidden"
            style={{
              height: `${(size + outlineSize) / 2}px`,
              width: `${size}px`
            }}
          />
          <div className="icon__label">
            <span className="icon__label-text">{name}</span>
          </div>
          <Tippy
            placement="left"
            delay="250"
            content={tooltipContent}
            disabled={editMode}
          >
            {deviceDrag(drop(iconDrag(
              <div
                onClick={handleOnClick}
                onMouseDown={handleMouseDown}
                className={classNames('icon__svg-wrapper',
                  'icon__svg-wrapper-absolute', {
                  'icon__svg-wrapper--hidden': hidden
                })}
                style={svgStyle(size)}
                onDragEnter={(event) => {
                  event.stopPropagation();
                }}
                onDragLeave={(event) => {
                  event.stopPropagation();
                }}
              >
                <IconSvg type={iconType} status={status} size={size} />
                <Interface
                  fromDevice={name}
                  x={x}
                  y={y}
                  pcX={50}
                  pcY={50}
                  size={size * CIRCLE_ICON_RATIO}
                  active={selected && editMode}
                  type={BTN_ADD}
                  tooltip="Add Connection (drag me)"
                />
              </div>
            )))}
          </Tippy>
        </div>
      )}
    </Fragment>
  );
}

export default Icon;
