import React from 'react';

import Sidebar from 'features/common/Sidebar';
import NodeListWrapper from 'features/menu/panels/NodeListWrapper';
import ServiceList from './ServiceList';

import * as Topology from './sidebar-modules/Topology';
import * as Igp from './sidebar-modules/Igp';
import * as SegmentRouting from './sidebar-modules/SegmentRouting';
import * as Bgp from './sidebar-modules/Bgp';

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
