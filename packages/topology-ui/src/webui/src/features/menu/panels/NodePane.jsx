import React from 'react';
import { Fragment, memo, useCallback } from 'react';
import { useDispatch } from 'react-redux';

import { CONFIGURATION_EDITOR_URL } from 'constants/Layout';
import * as IconTypes from 'constants/Icons';

import FieldGroup from '../../common/FieldGroup';
import Accordion from '../../common/Accordion';
import InlineBtn from '../../common/buttons/InlineBtn';

import { stopThenGoToUrl } from 'api/comet';
import { useDeletePathMutation } from 'api/data';


const NodePane = memo(function NodePane({
  title, label, keypath, level, isOpen, fade, nodeToggled,
  disableGoTo, extraButtons, subHeader, children, ...rest
}) {
  console.debug('NodePane Render');

  const toggle = useCallback(() => {
    Object.keys(rest).length > 0 && nodeToggled(keypath);
  }, [ keypath, nodeToggled ]);

  const dispatch = useDispatch();
  const goToNode = useCallback((event) => {
    event.stopPropagation();
    dispatch(stopThenGoToUrl(CONFIGURATION_EDITOR_URL + keypath));
  });

  const [ deletePath ] = useDeletePathMutation();
  const deleteNode = useCallback(async (event) => {
    event.stopPropagation();
    await deletePath({ keypath });
    if (isOpen) { toggle(); }
  });

  return (
    <Accordion
      level={level ? level : 1}
      isOpen={isOpen}
      fade={fade}
      toggle={toggle}
      variableHeight={true}
      header={
        <Fragment>
          <span className="header__title-text">{title || label}</span>
          {!disableGoTo &&
            <InlineBtn
              type={IconTypes.BTN_GOTO}
              classSuffix="go-to"
              tooltip={`View ${label} in Configuration Editor`}
              onClick={goToNode}
            />
          }
          {extraButtons}
          <InlineBtn
            type={IconTypes.BTN_DELETE}
            classSuffix="delete"
            tooltip={`Delete ${label}`}
            onClick={deleteNode}
          />
        </Fragment>
      }>
      {subHeader}
      {rest && <FieldGroup { ...rest } />}
      {children}
    </Accordion>
  );
});

export default NodePane;
