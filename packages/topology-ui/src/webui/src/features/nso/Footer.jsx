import React from 'react';
import { PureComponent } from 'react';
import { connect } from 'react-redux';
import classNames from 'classnames';

import { stopThenGoToUrl } from 'api/comet';

const mapDispatchToProps = { stopThenGoToUrl };

class Footer extends PureComponent {
  constructor(props) {
    super(props);
    this.state = { closed: false };
  }

  close = () => {
    this.setState({ closed: true });
  };

  open = () => {
    this.setState({ closed: false });
  };

  render() {
    const { applications, current, hasWriteTransaction, stopThenGoToUrl } = this.props;
    const { closed } = this.state;
    console.debug('NSO Footer Render');
    return (
      <div className="nso-footer">
        <button className={classNames('nso-footer__toggle-btn', {
          'nso-footer__toggle-btn--closed': closed
        })} onClick={this.open}>
          <div className="nso-footer__toggle-btn-text">⌃</div>
        </button>
        <div className={classNames('nso-footer__sc-menu', {
          'nso-footer__sc-menu--closed': closed
        })}>
          <button
            className="nso-footer__sc-menu-toggle-btn"
            onClick={this.close}
          />
          {applications?.map(({ href, title, abbreviation }) =>
            <a key={abbreviation} className={classNames('nso-footer__sc-item', {
              'nso-footer__sc-item--current': title === current
            })} onClick={async () => {
              stopThenGoToUrl(href);
            }}>
              <div className="nso-footer__sc-letter">{abbreviation +
                (abbreviation === 'C' && hasWriteTransaction ? '*' : '')}</div>
              <div className="nso-footer__sc-text">{title}</div>
            </a>
          )}
          <button
            className="nso-footer__sc-menu-toggle-btn"
            onClick={this.close}
          >
            <div className=
              "nso-footer__toggle-btn-text nso-footer__toggle-btn-text--down"
            >⌃</div>
          </button>
        </div>
      </div>
    );
  }
}

export default connect(undefined, mapDispatchToProps)(Footer);
