import './menu.css';
import React from 'react';

import Sidebar from '../common/Sidebar';
import NodeListWrapper from './panels/NodeListWrapper';
import ServiceList from './panels/ServiceList';

import * as Topology from './modules/Topology';
import * as Igp from './modules/Igp';
import * as SegmentRouting from './modules/SegmentRouting';
import * as Bgp from './modules/Bgp';

function MenuSidebar() {
  console.debug('MenuSidebar Render');

  return (
    <Sidebar>
      <NodeListWrapper
        title="Topologies"
        label={Topology.label}
        keypath={Topology.path}
        fetching={Topology.useFetchStatus()}
      >
        {Topology.useQuery().data?.map(({ name }) =>
          <Topology.Component key={name} name={name} />)}
      </NodeListWrapper>
      <ServiceList module={Igp} />
      <ServiceList module={SegmentRouting} />
      <ServiceList module={Bgp} />
    </Sidebar>
  );
}

export default MenuSidebar;
