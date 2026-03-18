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
    const { offsetWidth: width, offsetHeight: height } = ref.current;
    const { left, top } = ref.current.getBoundingClientRect();
    dispatch(dimensionsChanged({ width, height, left, top }));
  };

  return (
    <LayoutContextProvider>
      <div className="topology">
        <div className="header">
          <span className="header__title-text">Select a topology...</span>
        </div>
        <div className="component__layer">
          {layouts.data?.map(({ name }) =>
            <Container key={name} name={name} />
          )}
        </div>
        <div className="component__layer topology__body-placeholder">
          <div className="topology__body" ref={ref}>
            <ReactResizeDetector handleWidth handleHeight
              onResize={resize}
              refreshMode="debounce"
              refreshRate={500}
            />
              {devices.data && connections.data?.map(
                ({ keypath, aEndDevice, zEndDevice,
                   igpMetric, teMetric, delayMetric }) =>
                  <Connection
                    key={`${aEndDevice} - ${zEndDevice}`}
                    keypath={keypath}
                    aEndDevice={aEndDevice}
                    zEndDevice={zEndDevice}
                    igp={igpMetric}
                    te={teMetric}
                    delay={delayMetric}
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
