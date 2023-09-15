import React from 'react';
import { useContext } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import classNames from 'classnames';

import * as IconTypes from 'constants/Icons';

import InlineBtn from '../common/buttons/InlineBtn';

import { getDraggedItem, getVisibleUnderlays, getZoomedContainer,
         underlayToggled, containerZoomToggled } from './topologySlice';
import { LayoutContext } from './LayoutContext';


function Container({ name }) {
  console.debug('Container Render');

  const dispatch = useDispatch();
  const layout = useContext(LayoutContext);

  const zoomedContainer = useSelector((state) => getZoomedContainer(state));
  const draggedItem = useSelector((state) => getDraggedItem(state));
  const underlayVisible = useSelector(
    (state) => getVisibleUnderlays(state).includes(name));

  const container = layout.containers[name];

  const { index, title, pc : { backgroundWidth: width } } = container;

  return (
    <div
      className="container"
      style={{ width: `${width}%` }}
    >
      <div
        className={classNames('container__layer', {
          'container__background': (index % 2 === 0),
          'container__background--alt': (index % 2 !== 0),
          'container__background--not-first': (index !== 0 && width > 0)
        })}
      >
        <div className="header">
            <span className="header__title-text">{title}</span>
            <InlineBtn
              type={IconTypes.BTN_SHOW_UNDERLAY}
              classSuffix={underlayVisible ? 'hidden' : 'underlay'}
              tooltip={'Show underlay devices'}
              onClick={() => dispatch(underlayToggled(name))}
            />
            <InlineBtn
              type={IconTypes.BTN_HIDE_UNDERLAY}
              classSuffix={underlayVisible ? 'underlay' : 'hidden'}
              tooltip={'Hide underlay devices'}
              onClick={() => dispatch(underlayToggled(name))}
            />
            <InlineBtn
              type={IconTypes.BTN_ZOOM_IN}
              classSuffix={zoomedContainer ? 'hidden' : 'zoom'}
              tooltip={'Zoom in'}
              onClick={() => dispatch(containerZoomToggled(name))}
            />
            <InlineBtn
              type={IconTypes.BTN_ZOOM_OUT}
              classSuffix={zoomedContainer ? 'zoom' : 'hidden'}
              tooltip={'Zoom out'}
              onClick={() => dispatch(containerZoomToggled(name))}
            />
          </div>
      </div>
      <div className={classNames(
        'container__layer', 'container__overlay', {
        'container__overlay--inactive':
          draggedItem?.icon && draggedItem.container !== name
      })}/>
    </div>
  );
}

export default Container;
