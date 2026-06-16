import React from 'react';
import { useSelector } from 'react-redux';

import Sidebar from 'features/common/Sidebar';
import NodeListWrapper from 'features/menu/panels/NodeListWrapper';
import ServiceList from 'features/menu/panels/ServiceList';
import { getOpenTopologyName } from 'features/menu/menuSlice';

import * as ManagedTopology from './sidebar-modules/ManagedTopology';
import * as Topology from './sidebar-modules/Topology';
import * as Igp from './sidebar-modules/Igp';
import * as SegmentRouting from './sidebar-modules/SegmentRouting';
import * as Bgp from './sidebar-modules/Bgp';

function MenuSidebar() {
  console.debug('MenuSidebar Render');

  const openTopology = useSelector(getOpenTopologyName);

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
      <ServiceList
        module={Igp}
        stackedModule={ManagedTopology}
        contextName={openTopology}
      />
      <ServiceList
        module={SegmentRouting}
        stackedModule={ManagedTopology}
        contextName={openTopology}
      />
      <ServiceList
        module={Bgp}
        stackedModule={ManagedTopology}
        contextName={openTopology}
      />
    </Sidebar>
  );
}

export default MenuSidebar;
