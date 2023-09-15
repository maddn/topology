import './config.css';
import React from 'react';
import { memo  } from 'react';
import { useSelector } from 'react-redux';

import Sidebar from '../common/Sidebar';
import Config from './Config';
import { usePlatformsQuery } from '../topology/Icon';
import { getExpandedIcons, getConfigViewerVisible } from '../topology/topologySlice';
import { getOpenTopology, getOpenService } from '../menu/menuSlice';


const ConfigViewer = memo(function ConfigViewer(props) {
  console.debug('Config Viewer Render');
  const expandedIcons = useSelector((state) => getExpandedIcons(state));
  const configViewerVisible = useSelector((state) => getConfigViewerVisible(state));
  const openTopology = useSelector((state) => getOpenTopology(state));
  const openService = useSelector((state) => getOpenService(state));
  const platforms = usePlatformsQuery();

  return (
    <Sidebar right={true} hidden={!configViewerVisible}>
      <div className="header">
        <div className="header__title-text">Config Viewer</div>
      </div>
      <div className="sidebar__body">
        {platforms && expandedIcons && platforms.data?.filter(
          ({ parentName }) => expandedIcons.includes(parentName)
        ).map(({ parentName: device }) => {
          return <Config key={device} device={device} openService={openService} openTopology={openTopology}/>;
        })
      }
      </div>
    </Sidebar>
  );
});

export default ConfigViewer;
