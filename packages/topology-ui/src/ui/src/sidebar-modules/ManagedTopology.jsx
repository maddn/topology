import React from 'react';
import { useMemo } from 'react';

import ServicePane from 'features/menu/panels/ServicePane';
import CreatableService from 'features/menu/panels/CreatableService';

import { useQueryQuery, useQueryState, useMemoizeWhenFetched,
         createItemsSelector, selectItem } from 'api/query';

import * as Topology from './Topology';
import * as IpConnectivity from './IpConnectivity';
import * as BaseConfig from './BaseConfig';
import * as Igp from './Igp';
import * as Bgp from './Bgp';
import * as SegmentRouting from './SegmentRouting';

export const label = 'Managed Topology';
export const service = 'managed-topology';
export const path = `/topology:topologies/${service}`;

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

function formatDate(isoDateStr) {
  const date = new Date(isoDateStr);
  return `${
    date.getDate()}/${date.getMonth()+1} ${date.toTimeString().slice(0, 8)}`;
}

export function Component({ name }) {
  console.debug('Managed Topology Services Render');

  const { data } = useQuery(selectItem('name', name));
  const keypath = data?.keypath;
  const topologySelector = useMemo(() =>
    createItemsSelector('topology', name), [ name ]);

  const { data: igpServices } = Igp.useQuery(topologySelector, true);
  const { data: bgpServices } = Bgp.useQuery(topologySelector, true);
  const { data: srServices } = SegmentRouting.useQuery(topologySelector, true);

  const configReferences = useMemo(() => [
    `${IpConnectivity.path.replace(
      Topology.path, `${Topology.path}{${name}}`)}`,
    `${BaseConfig.path}{${name}}`,
    ...(igpServices?.map(({ name }) => `${Igp.path}{${name}}`) || []),
    ...(bgpServices?.map(({ asNumber }) => `${Bgp.path}{${asNumber}}`) || []),
    ...(srServices?.map(({ igp }) => `${SegmentRouting.path}{${igp}}`) || [])
  ], [ bgpServices, igpServices, name, srServices ]);

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
      configReferences={configReferences}
      queryTag="managed-topology"
      {...plan}
    /> :
      <CreatableService { ...{ label, keypath: `${path}{${name}}` } } />
  );
}
