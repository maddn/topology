import React from 'react';

import NodeListWrapper from './NodeListWrapper';
import Accordion from '../../common/Accordion';

import { useOpenTopologyName } from '../../topology/hooks';
import { useIsManagedTopology,
         path as managedTopologyPath } from '../modules/ManagedTopology';

import { useQueryState as _useQueryState, selectItem } from 'api/query';

export function getPath(service, managed) {
  const path = managed ? managedTopologyPath : '/topology:topologies';
  return service ? `${path}/${service}` : path;
}

export function useQueryState(service, queryKey) {
  const queryState = _useQueryState(getPath(service, queryKey));
  const managedQueryState = _useQueryState(
    getPath(!queryKey && service, true), queryKey);
  return (queryState === 'Error' || managedQueryState === 'Error') ? 'Error' :
         (queryState === 'OK' && managedQueryState === 'OK') ? 'OK' : '';
}

export function useData(
  useQuery, selectorValue, suffix, selectorKey='name', selectorKeyManaged='name'
) {
  const { data } = useQuery(selectItem(selectorKeyManaged, selectorValue), true);
  const { data: serviceData } = useQuery(selectItem(selectorKey, selectorValue));
  return [
    data && Object.keys(data).length > 0 ? data : serviceData,
    serviceData?.keypath || `${data?.keypath}${suffix ? `/${suffix}` : ''}/..`
  ];
}

export function ServiceList ({ module }) {
  console.debug('ServiceList Render');

  const openTopology = useOpenTopologyName();
  const managedTopologyData = module.useQuery(undefined, true).data;
  const serviceData = module.useQuery().data;
  const data = serviceData && managedTopologyData?.concat(serviceData);
  const managed = useIsManagedTopology(openTopology);

  return (
    <NodeListWrapper
      title={`${module.label}s`}
      label={module.label}
      keypath={`${managed ? `${managedTopologyPath}{${openTopology}}` : getPath()
        }/${module.service}`}
      fetching={module.useFetchStatus()}
      newItemDefaults={module.setTopologyInNewItem &&
        [ { path: 'topology', value: openTopology } ]}
    >
      {[...new Set(data?.map(({ topology }) => topology))].map(
        topologyGroup =>
          <Accordion
            key={topologyGroup}
            isOpen={topologyGroup === openTopology}
            variableHeight={true}
          >
            {data.filter(({ topology, name }, index) =>
              topology === topologyGroup && data.findIndex(entries =>
                entries.name == name && entries.topology == topology
              ) === index).map(
                ({ name }) => <module.Component key={name} name={name} />)}
          </Accordion>
      )}
    </NodeListWrapper>

  );
}

export default ServiceList;
