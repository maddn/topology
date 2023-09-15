import React from 'react';
import classNames from 'classnames';

import UserMenu from './UserMenu';

import ciscoImg from 'resources/cisco.svg';
import { useRevertMutation, useApplyMutation } from 'api';


function Header({ user, version, title, hasWriteTransaction, commitInProgress }) {
  console.debug('NSO Header Render');
  const [ revert ] = useRevertMutation();
  const [ apply ] = useApplyMutation();
  return (
    <div className="nso-header">
      <div className="nso-header__inner">
        <a href="/webui-one/" className="nso-header__link">
          <img
            src={ciscoImg}
            className="nso-header__cisco-logo"
            alt="Cisco"
          />
        </a>
        <div className="nso-header__left">
          <div className="nso-header__title">{title}</div>
          <div className="nso-header__version">VERSION: {version}</div>
        </div>
        <div className="nso-header__right">
          <div className="nso-header__item">
            <button onClick={revert} className={classNames('nso-btn',
            'nso-btn--header', {
            'nso-btn--disabled': !hasWriteTransaction || commitInProgress
          })}>Revert</button>
          </div>
          <div className="nso-header__item">
          <button onClick={apply} className={classNames('nso-btn',
              'nso-btn--header', {
              'nso-btn--disabled': !hasWriteTransaction || commitInProgress
          })}>{commitInProgress ?
            <div>
              <span className="loading__dot"/>
              <span className="loading__dot"/>
              <span className="loading__dot"/>
            </div>
            : 'Commit'}
          </button>
          </div>
          <div className="nso-header__item">
            <UserMenu user={user} hasWriteTransaction={hasWriteTransaction}/>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Header;
