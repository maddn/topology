import React from 'react';
import { useRef } from 'react';
import { useDispatch } from 'react-redux';
import ReactResizeDetector from 'react-resize-detector';

import Container from './Container';
import Connection, { useConnectionsQuery } from './Connection';
import Icon, { useDevicesQuery, usePlatformsQuery } from './Icon';
import DragLayerCanvas from './DragLayerCanvas';
import CustomDragLayer from './CustomDragLayer';
import LoadingOverlay from '../common/LoadingOverlay';

import { LayoutContextProvider, useLayoutsQuery } from './LayoutContext';
import { dimensionsChanged } from './topologySlice';
import { fetchStatus } from 'api/query';


const TopologyBody = React.memo(function TopologyBody () {
  console.debug('TopologyBody Render');

  const dispatch = useDispatch();

  const ref = useRef(null);
  const canvasRef = useRef();

  const layouts = useLayoutsQuery();
  const devices = useDevicesQuery();
  const connections = useConnectionsQuery();
  const platforms = usePlatformsQuery();

  const resize = () => {
    console.debug('Topology Resize');
    const { offsetWidth, offsetHeight } = ref.current;
    dispatch(dimensionsChanged({ width: offsetWidth, height: offsetHeight }));
  };

  return (
    <LayoutContextProvider>
      <div className="topology__body">
        <div className="header">
          <span className="header__title-text">Select a topology...</span>
        </div>
        <div className="topology__layer topology__layer--background">
          {layouts.data?.map(({ name }) =>
            <Container key={name} name={name} />
          )}
        </div>
        <div className="topology__layer topology__layer--foreground">
          <div className="topology__header"/>
          <div className="topology__body" ref={ref}>
            <ReactResizeDetector handleWidth handleHeight
              onResize={resize}
              refreshMode="debounce"
              refreshRate={500}
            />
            <div className="topology__layer">
              {devices.data && connections.data?.map(
                ({ keypath, aEndDevice, zEndDevice }) =>
                  <Connection
                    key={`${aEndDevice} - ${zEndDevice}`}
                    keypath={keypath}
                    aEndDevice={aEndDevice}
                    zEndDevice={zEndDevice}
                  />
              )}
              {devices.data?.map(({ id, name }) =>
                  <Icon key={id} name={name} />
              )}
              <DragLayerCanvas canvasRef={canvasRef} />
              <CustomDragLayer canvasRef={canvasRef} />
            </div>
          </div>
        </div>
      </div>
      <LoadingOverlay items={{
        'Layouts':      fetchStatus(layouts),
        'Devices':      fetchStatus(devices),
        'Connections':  fetchStatus(connections),
        'Platforms':    fetchStatus(platforms)
      }}/>
    </LayoutContextProvider>
  );
});

export default TopologyBody;
