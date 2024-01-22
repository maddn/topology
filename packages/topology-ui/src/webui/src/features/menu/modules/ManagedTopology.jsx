import React from 'react';

import ServicePane from '../panels/ServicePane';
import CreatableService from '../panels/CreatableService';

import { useQueryQuery, useQueryState, useMemoizeWhenFetched,
         selectItem } from 'api/query';

export const label = 'Managed Topology';
export const path = '/topology:topologies/managed-topology';

export function useQuery(itemSelector) {
  return useQueryQuery({
    xpathExpr: path,
    selection:  [ 'string(topology)', 'topology' ],
  }, { selectFromResult: itemSelector });
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'Managed Topology Services': useQueryState(path)
  });
}

export function useIsManagedTopology(name) {
  return useQuery(selectItem('name', name)).data !== undefined;
}

function formatDate(isoDateStr) {
  const date = new Date(isoDateStr);
  return `${
    date.getDate()}/${date.getMonth()+1} ${date.toTimeString().slice(0, 8)}`;
}

export const Component = React.memo(function Component({ name }) {
  console.debug('Managed Topology Services Render');

  const { data } = useQuery(selectItem('name', name));
  const keypath = data?.keypath;

  const plan = Object.fromEntries(useQueryQuery({
    xpathExpr: `${path}/plan/component/state[status = 'reached'][last()]`,
    selection: [ 'name', '../name', 'when' ]
  }).data?.map(({ name, parentName, when }) => [
    `[${formatDate(when)}]  ${parentName}`, name.slice(name.indexOf(':')+1) ]
  ) || []);

  return (data ?
    <ServicePane
      key={name}
      keypath={keypath}
      serviceKeypath={keypath}
      title={label}
      label={label}
      queryTag="managed-topology"
      {...plan}
    /> :
      <CreatableService { ...{ label, keypath: `${path}{${name}}` } } />
  );
});
