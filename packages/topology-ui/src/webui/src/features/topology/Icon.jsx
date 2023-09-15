import React from 'react';
import { Fragment, memo,
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

import { getSelectedIcon, getEditMode, getHighlightedIcons,
         itemDragged, iconHovered, connectionSelected, iconSelected,
         iconExpandToggled } from './topologySlice';
import { getOpenTopology } from '../menu/menuSlice';

import { useIconPosition, useConnectedDevices, useIsExpanded,
         useOpenTopologyName,} from './hooks';

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
  return __useDevicesQuery(selectItemWithArray([
    [ 'parentName', useOpenTopologyName() ], [ 'name', name ]
  ])).data;
}

export function usePlatformsQuery(itemSelector) {
  return useQueryQuery({
    xpathExpr: '/ncs:devices/device/platform',
    selection: [ '../name', 'name', 'model', 'version' ]
  }, { selectFromResult: itemSelector });
}

export function usePlatform(deviceName) {
  return usePlatformsQuery(selectItem('parentName', name)).data;
}


// === Utils ==================================================================

function positionStyle(position, size) {
  return {
    left: `${position.pcX}%`,
    top: `${position.pcY}%`,
    transform: `translate(-50%, ${-size/2}px)`,
  };
}

function sizeStyle(size) {
  return {
    height: `${size}px`,
    width: `${size}px`,
  };
}


// === Component ==============================================================

const Icon = memo(function Icon ({ name }) {
  console.debug('Icon render');
  const mouseDownPos = {};

  const dispatch = useDispatch();
  const [ setValue ] = useSetValueMutation();
  const [ create ] = useCreateMutation();
  const [ deletePath ] = useDeletePathMutation();

  const { iconSize: size, pxToPc } = useContext(LayoutContext);

  const platform = usePlatform(name);
  const device = useDevice(name);
  const { keypath, iconType, provisioningStatus, operationalStatus } = device;
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

  const [ collected, iconDrag, iconDragPreview ] = useDrag(() => ({
    type: ICON,
    item: () => {
      const img = new Image();
      img.src = `data:image/svg+xml,${encodeURIComponent(renderToStaticMarkup(
            <IconSvg type={iconType} status={status} size={size} />
      ))}`;
      const item = {
        icon: { name, img, imgReady: false, container },
        x, y,  mouseDownPos
      };
      img.onload = () => { item.icon.imgReady = true; };
      requestAnimationFrame(
        () => { dispatch(itemDragged({ icon: name, container })); });
      return item;
    },
    end: (item, monitor) => {
      const offset = monitor.getDifferenceFromInitialOffset();
      const { x, y } = item;
      dispatch(itemDragged(undefined));
      moveIcon(x + offset.x, y + offset.y);
    },
    canDrag: editMode,
    collect: (monitor) => ({ isDragging: monitor.isDragging() })
  }), [ mouseDownPos ]);

  const [ collectedProps, drop ] = useDrop(() => ({
    accept: INTERFACE,
    drop: (item) => {
      const { connection: { aEndDevice: aEnd, zEndDevice: zEnd,
                            keypath, fromDevice } } = item;
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
      dispatch(connectionSelected(aEndDevice, zEndDevice));
    },
    canDrop: (item, monitor) => {
      const hoveredInterface = monitor.isOver() && item;
      if (!hoveredInterface) {
        return false;
      }
      const { fromDevice } = hoveredInterface.connection;
      if (name === fromDevice ) {
        return false;
      }
      return !connectedDevices.includes(fromDevice);
    },
    collect: (monitor) => ({
      canDrop: monitor.canDrop()
    })
  }));

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

  const { canDrop } = collectedProps;

  useEffect(() => {
    dispatch(iconHovered(canDrop && name));
  }, [ canDrop ]);

  useEffect(() => {
    iconDragPreview(getEmptyImage(), {});
  });

  const { isDragging } = collected;

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
          ...sizeStyle(outlineSize),
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
                style={sizeStyle(size)}
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
});

export default Icon;
