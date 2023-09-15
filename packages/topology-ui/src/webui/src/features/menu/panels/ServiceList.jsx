import React from 'react';

import NodeListWrapper from './NodeListWrapper';
import Accordion from '../../common/Accordion';

import { useOpenTopologyName } from '../../topology/hooks';

export function ServiceList ({ module }) {
  console.debug('ServiceList Render');

  const openTopology = useOpenTopologyName();
  const { data } = module.useQuery();

  return (
    <NodeListWrapper
      title={`${module.label}s`}
      label={module.label}
      path={module.path}
      fetching={module.useFetchStatus()}
      newItemDefaults={[ { path: 'topology', value: openTopology } ]}
    >
      {[...new Set(data?.map(({ topology }) => topology))].map(
        topologyGroup =>
          <Accordion
            key={topologyGroup}
            isOpen={topologyGroup === openTopology}
            variableHeight={true}
          >
            {data.filter(({ topology }) => topology === topologyGroup).map(
              ({ name }) => <module.Component key={name} name={name} />)}
          </Accordion>
      )}
    </NodeListWrapper>

  );
}

export default ServiceList;
