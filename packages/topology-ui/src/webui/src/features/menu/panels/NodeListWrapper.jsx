import React from 'react';
import { useState, useCallback, useRef, Fragment } from 'react';
import { useDispatch } from 'react-redux';

import LoadingOverlay from '../../common/LoadingOverlay';
import NewItem from '../../common/NewItem';
import InlineBtn from '../../common/buttons/InlineBtn';

import { BTN_ADD } from 'constants/Icons';
import { bodyOverlayToggled } from '../../nso/nsoSlice';
import { isFetching } from 'api/query';


function NodeListWrapper({
  title, label, path, level, disableCreate, fetching, newItemDefaults, children
}) {
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
                type={BTN_ADD}
                classSuffix="create"
                tooltip={`Add New ${label}`}
                onClick={openNewItem}
              />
              <NewItem
                btnRef={btnRef}
                path={path}
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
        className="sidebar__body"
        style={{minHeight: `${minHeight}px`,
        transition: `min-height ${minHeight === 0 ? 1000 : 0}ms`
      }}
      >
        {children}
        <LoadingOverlay items={fetching} ref={measuredRef}/>
      </div>
    </Fragment>
  );
}

export default NodeListWrapper;
