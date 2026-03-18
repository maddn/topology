import React from 'react';
import { useState, useCallback, useRef,
         Fragment, forwardRef } from 'react';
import { useDispatch } from 'react-redux';

import LoadingOverlay from '../../common/LoadingOverlay';
import NewItem from '../../common/NewItem';
import InlineBtn from '../../common/buttons/InlineBtn';

import { BTN_ADD } from 'constants/Icons';
import { bodyOverlayToggled } from '../../nso/nsoSlice';
import { isFetching } from 'api/query';


const NodeListWrapper = forwardRef(function NodeListWrapper({
  title, label, keypath, level, fetching, disableCreate, newItemDefaults,
  children
}, ref) {
  console.debug('NodeListWrapper Render');

  const [ newItemOpen, setNewItemOpen ] = useState(false);
  const [ minHeight, setMinHeight ] = useState(0);

  const dispatch = useDispatch();
  const btnRef = useRef(null);

  const openNewItem = () => {
    setNewItemOpen(true);
    dispatch(bodyOverlayToggled(true));
  };

  const closeNewItem = useCallback(() => {
    setNewItemOpen(false);
    dispatch(bodyOverlayToggled(false));
  }, []);

  const measuredRef = useCallback(node => {
    if (node !== null) {
      const height = isFetching(fetching) ? node.scrollHeight : 0;
      setTimeout(() => setMinHeight(height), height < minHeight ? 1000 : 0);
    }
  }, [ minHeight, fetching ]);

  return (
    <Fragment>
      {title &&
        <div className="header">
          <span className="header__title-text">{title}</span>
          {!disableCreate &&
            <Fragment>
              <InlineBtn
                ref={btnRef}
                icon={BTN_ADD}
                classSuffix="create"
                tooltip={`Add New ${label}`}
                onClick={openNewItem}
              />
              <NewItem
                btnRef={btnRef}
                path={keypath}
                label={`${label} Name`}
                isOpen={newItemOpen}
                close={closeNewItem}
                defaults={newItemDefaults}
              />
            </Fragment>
          }
        </div>
      }
      <div
        className="accordion__group"
        style={{minHeight: `${minHeight}px`,
        transition: `min-height ${minHeight === 0 ? 1000 : 0}ms`
      }}
      >
        <LoadingOverlay items={fetching} ref={measuredRef}/>
        {children}
      </div>
    </Fragment>
  );
});

export default NodeListWrapper;
