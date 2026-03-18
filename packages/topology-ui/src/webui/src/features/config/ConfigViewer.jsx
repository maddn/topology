import './config.css';
import React from 'react';
import { useSelector } from 'react-redux';

import Sidebar from 'features/common/Sidebar';
import Config from './Config';
import { usePlatformsQuery, useDevicesQuery } from 'features/topology/Icon';
import { getExpandedIcons, getConfigViewerVisible } from 'features/topology/topologySlice';
import { getOpenTopology, getOpenService } from 'features/menu/menuSlice';


function ConfigViewer() {
  console.debug('Config Viewer Render');
  const expandedIcons = useSelector((state) => getExpandedIcons(state));
  const configViewerVisible = useSelector((state) => getConfigViewerVisible(state));
  const openTopology = useSelector((state) => getOpenTopology(state));
  const openService = useSelector((state) => getOpenService(state));
  const platforms = usePlatformsQuery().data;
  const devices = useDevicesQuery().data;

  return (
    <Sidebar right={true} hidden={!configViewerVisible}>
      <div className="header">
        <div className="header__title-text">Config Viewer</div>
      </div>
      <div className="accordion__group">
        {devices && platforms && expandedIcons && expandedIcons.map(
          device => <Config
            key={device}
            device={device}
            keypath={devices.find(({ name }) => name === device)?.keypath}
            managed={platforms.find(({ parentName }) => parentName === device)}
            openService={openService}
            openTopology={openTopology}/>
        )}
      </div>
    </Sidebar>
  );
}

export default ConfigViewer;
