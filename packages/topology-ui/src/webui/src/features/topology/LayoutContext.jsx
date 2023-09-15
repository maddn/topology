import React from 'react';
import { createContext, useMemo } from 'react';
import { useSelector } from 'react-redux';

import { getIconSize, getDimensions, getZoomedContainer } from './topologySlice';
import { useOpenTopologyName } from './hooks';
import { useQueryQuery, createItemsSelector } from 'api/query';


export const LayoutContext = createContext();

const safeRound = (n) =>
  Math.min(1, Math.max(0, Number.parseFloat(n).toFixed(4))).toString();

export function useLayoutsQuery() {
  const topology = useOpenTopologyName();
  const selector = useMemo(() =>
    createItemsSelector('parentName', topology), [ topology ]);
  return useQueryQuery({
    xpathExpr: '/topology:topologies/topology/layout/container',
    selection: [
      'hypervisor',
      '../../name',
      'width',
      'title',
      'connection-colour' ]
  }, { selectFromResult: selector });
}

const calculateLayout = (
  basicLayout, dimensions, iconHeightPc, iconWidthPc, zoomedContainerName
) => {
  console.debug('Reselect layout');
  if (!basicLayout || !dimensions) {
    return undefined;
  }
  let afterZoomed = false;
  let x = -iconWidthPc / 2;
  return basicLayout.reduce((accumulator,
    { name, zoomed, title, connectionColour, width }, index) => {
    const containerZoomed = zoomedContainerName === name;
    if (containerZoomed) {
      afterZoomed = true;
    }
    width = Number(width);
    const pc = zoomedContainerName ? {
      left: containerZoomed ? iconWidthPc / 2 : afterZoomed ? 100 : 0,
      right: containerZoomed ? 100 - iconWidthPc / 2 : afterZoomed ? 100 : 0,
      top: iconHeightPc / 2,
      bottom: 100 - iconHeightPc,
      width: containerZoomed ? 100 - iconWidthPc : 0,
      height: 100 - iconHeightPc * 1.5,
      backgroundWidth: containerZoomed && !zoomed ? 100 : 0
    } : {
      left: x += iconWidthPc,
      right: x += width - iconWidthPc,
      top: iconHeightPc / 2,
      bottom: 100 - iconHeightPc,
      width: width - iconWidthPc,
      height: 100 - iconHeightPc * 1.5,
      backgroundWidth: (index === 0)
        ? width + iconWidthPc / 4
        : (index === (basicLayout.length - 1))
          ? width - iconWidthPc / 4
          : (index % 2)
            ? width - iconWidthPc / 2
            : width + iconWidthPc / 2
    };
    accumulator[name] = {
      name, index, title, connectionColour, pc,
      px: {
        left: Math.round(pc.left * dimensions.width / 100),
        right: Math.round(pc.right * dimensions.width / 100),
        top: Math.round(pc.top * dimensions.height / 100),
        bottom: Math.round(pc.bottom * dimensions.height / 100)
      }
    };
    return accumulator;
  }, {});
};

export const LayoutContextProvider = React.memo(function Context({ children }) {
  console.debug('LayoutContext Render');
  const zoomedContainerName = useSelector((state) => getZoomedContainer(state));
  const dimensions = useSelector((state) => getDimensions(state));
  const iconSize = useSelector((state) => getIconSize(state));

  const { data } = useLayoutsQuery();

  const context = useMemo(() => {
    const { width, height } = dimensions || {};

    const iconHeightPc = height > width ? iconSize*width/height : iconSize;
    const iconWidthPc = width > height ? iconSize*height/width : iconSize;

    const containers = calculateLayout(data,
      dimensions, iconHeightPc, iconWidthPc, zoomedContainerName);

    const pxToScreenPc = ({ x, y }) => ({
      pcX: x / width * 100,
      pcY: y / height * 100
    });

    const restrictPos = ({ x, y }, containerName) => {
      const { left, right, top, bottom } = containers[containerName].px;
      return {
        x: Math.max(left, Math.min(right, x)),
        y: Math.max(top, Math.min(bottom, y))
      };
    };

    return {
      dimensions, iconHeightPc, iconWidthPc, restrictPos, containers,
      iconSize: width > height ? iconSize*height/100 : iconSize*width/100,
      pxToPc: (coord, containerName) => {
        if (containerName) {
          const { left, top, width, height } = containers[containerName].pc;
          const { pcX, pcY } = pxToScreenPc(restrictPos(coord, containerName));
          return { x: safeRound((pcX - left) / width),
                   y: safeRound((pcY - top) / height) };
        }
        return pxToScreenPc(coord);
      }
    };
  }, [ data, iconSize, dimensions, zoomedContainerName ]);

  return (
    <LayoutContext.Provider value={context}>
      {children}
    </LayoutContext.Provider>
  );
});
