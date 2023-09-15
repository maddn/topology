import React from 'react';
import { useState, useCallback } from 'react';
import { useDrop } from 'react-dnd';
import classNames from 'classnames';

import { DEVICE } from 'constants/ItemTypes';
import { ROUTER } from 'constants/Icons';

import NodePane from './NodePane';
import NodeListWrapper from './NodeListWrapper';

import { pathKeyRegex, swapLabels, useQueryQuery } from 'api/query';
import { useCreateMutation } from 'api/data';


const DroppableNodeList = React.memo(function DroppableNodeList({
  label, keypath, noTitle, baseSelect, labelSelect, selector, isLeafList,
  allowDrop, disableCreate, disableGoTo, ...rest
}) {
  console.debug('DrobbableNodeList Render');
  const [ openNode, setOpenNode ] = useState(null);
  const [ create ] = useCreateMutation();
  const createNode = useCallback((name) => create({ name, keypath, ...rest }));

  const { data } = useQueryQuery({
    xpathExpr: keypath.replace(pathKeyRegex, ''),
    selection: [ ...baseSelect, ...Object.keys(labelSelect || []) ],
    isLeafList
  }, { selectFromResult: selector });

  const [{ isOver, canDrop }, drop] = useDrop(() => ({
    accept: DEVICE,
    drop: ({ type, name }) => {
      if (type === ROUTER) {
        createNode(name);
      }
    },
    canDrop: ({ type }, monitor) => {
      return allowDrop && type === ROUTER;
    },
    collect: (monitor) => ({
      isOver: monitor.isOver(),
      canDrop: monitor.canDrop()
    })
  }));

  const toggled = useCallback((keypath) => {
    setOpenNode(openNode => openNode === keypath ? null : keypath);
  }, [ keypath ]);

  return (
    <div className="accordion__wrapper" ref={drop}>
      <NodeListWrapper
        title={!noTitle && `${label}s`}
        keypath={keypath}
        label={label}
        level="2"
        disableCreate={disableCreate}
     >
        {data?.map(({ name, keypath, ...item }) =>
          <NodePane
            title={name}
            key={name}
            keypath={keypath}
            label={label}
            level="2"
            isOpen={openNode === keypath}
            fade={!!openNode}
            nodeToggled={toggled}
            disableGoTo={disableGoTo}
            { ...swapLabels(item, labelSelect) }
          />
        )}
      </NodeListWrapper>
      <div className="accordion__overlay-wrapper">
        <div className={classNames('accordion__overlay', {
          'accordion__overlay--hovered': isOver && canDrop
        })}/>
      </div>
  </div>
  );
});

export default DroppableNodeList;
