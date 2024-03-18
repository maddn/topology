import React from 'react';
import { PureComponent, Fragment } from 'react';
import { connect } from 'react-redux';
import classNames from 'classnames';
import * as IconTypes from '../../constants/Icons';

import hljs from 'highlight.js';

import { CONFIGURATION_EDITOR_EDIT_URL } from 'constants/Layout';
import Accordion from '../common/Accordion';
import InlineBtn from '../common/buttons/InlineBtn';

import { handleError } from '../nso/nsoSlice';
import { action } from '../../api/data';
import { stopThenGoToUrl } from 'api/comet';
import { libvirtAction } from '../topology/hooks';


const mapDispatchToProps = {
  handleError, stopThenGoToUrl, libvirtAction, action: action.initiate
};

const trim = (configLines) => {
  const indent = configLines.length > 0 ? configLines[0].search(/\S/) : 0;
  return configLines.map(line => line.substr(indent));
};

const reIndent = (configLines, level=2) => {
  let indent = -level;
  let lastIndent = -1;
  return configLines.map(line => {
    const leadingSpace = line.search(/\S/);
    if (leadingSpace > lastIndent ) {
      indent += level;
    } else if (leadingSpace < lastIndent) {
      if (indent > 0) {
        indent -= level;
      }
    }
    lastIndent = leadingSpace;
    return ' '.repeat(indent) + line.trim();
  });
};

const reIndentXml = (configLines, level=2) => {
  let nextIndent = 0;
  return configLines.map(line => {
    let indent = nextIndent;
    const trimmed = line.trim();
    if (trimmed.startsWith('</')) {
      indent -= level;
      nextIndent = indent;
    } else if (trimmed.search(/^[^<]+<\//) !== -1) {
      nextIndent -= level;
    } else if (trimmed.search(/^<[^>]*[^/]>[^<]*$/) !== -1) {
      nextIndent += level;
    }
    return ' '.repeat(indent) + line.trim();
  });
};

const pretty = (configLines, format) => {
  if (['cli', 'yaml'].includes(format)) {
    return trim(configLines);
  } else if (format == 'json') {
    return reIndent(configLines, 1);
  } else if (format == 'xml') {
    return reIndentXml(configLines);
  } else {
    return reIndent(configLines);
  }
};

const slice = (configLines, format) => {
  if (format == 'cli') {
    while (configLines[0].trim().startsWith('!')) {
      configLines.shift();
    }
    return configLines.slice(1, -2);
  } else if (format == 'curly-braces') {
    return configLines.slice(2, -3);
  } else if (format == 'json') {
    return configLines.splice(4, 1).concat(configLines.slice(5, -5));
  } else if (format == 'yaml') {
    return configLines.slice(3, -2);
  } else if (format == 'xml') {
    return configLines.slice(4, -3);
  } else {
    return configLines;
  }
};

const convertXpaths = (config) => {
  let ret = config?.replace( /\[[^=[]*='(.[^']*)'\]/g, '{$1}' );
  ret = ret?.replace( /topology:/g, '' );
  return ret?.replace( /\/topologies\//g, '/topology:topologies/' );
};

const formatConfig = (config, format) => {
  const configLines = slice(convertXpaths(config).split('\n'), format);
  return pretty(configLines, format).join('\n');
};

class Config extends PureComponent {
  constructor(props) {
    super(props);
    this.state = {
      devicePath: `/ncs:devices/device{${props.device}}/config`,
      subscriptionHandle: undefined,
      config: undefined,
      format: undefined,
      serviceMetaData: false
    };
    this.libvirtAction = this.libvirtAction.bind(this);
    this.goToDevice = this.goToDevice.bind(this);
  }

  async componentDidMount() {
    this.props.managed && this.getConfig(undefined);
  }

  async getConfig(format) {
    const { action, device, handleError } = this.props;
    this.setState({ isFetching: true });
    try {
      const result = await action({
        path: `/ncs:devices/ncs:device{${
          device}}/topology:get-configuration`,
        params: { format, 'service-meta-data': true }
      });
      this.setState({
        isFetching: false,
        config: formatConfig(result.data.config, result.data.format),
        format: result.data.format,
      });
    } catch(exception) {
      this.setState({ isFetching: false });
      handleError('Failed to fetch device configuration', exception);
    }
  }

  getBackpointerRegex() {
    const { format } = this.state;
    if (format == 'cli') {
      return /<span class="hljs-comment">! Backpointer: \[(.*)\][^\]]*<\/span>/;
    } else if (format == 'curly-braces') {
      return /<span class="hljs-comment">\/\* Backpointer: \[(.*)\] \*\/<\/span>/;
    } else if (format == 'xml') {
      return / <span class="hljs-attr">backpointer<\/span>=<span class="hljs-string">&quot;(.*)&quot;<\/span>/;
    }
  }

  getRefcountRegex() {
    const { format } = this.state;
    if (format == 'cli') {
      return /<span class="hljs-comment">! Refcount: .*<\/span>/;
    } else if (format == 'curly-braces') {
      return /<span class="hljs-comment">\/\* Refcount: .*<\/span>/;
    } else if (format == 'xml') {
      return / <span class="hljs-attr">refcounter<\/span>=<span class="hljs-string">&quot;\d*&quot;<\/span>/;
    }
  }

  async libvirtAction(event, action) {
    event.stopPropagation();
    const { device, libvirtAction } = this.props;
    libvirtAction(action, device);
  }

  async goToDevice(event, action) {
    event.stopPropagation();
    const { keypath, stopThenGoToUrl } = this.props;
    stopThenGoToUrl(`${CONFIGURATION_EDITOR_EDIT_URL}${keypath}`);
  }

  highlightService(highlightedConfig) {
    const { format, serviceMetaData } = this.state;
    const { openService } = this.props;

    const backpointerRegex = this.getBackpointerRegex();
    const refcountRegex = this.getRefcountRegex();
    const indentRegex = /^<span class="hljs[^"]*">/;

    const iter = highlightedConfig.split('\n')[Symbol.iterator]();
    let { value, done } = iter.next();
    let result = [];

    const processBlock = highlight => {
      const blockIndent = value.replace(indentRegex, '').search(/\S/);
      let indent = blockIndent + 1;
      let backpointer = undefined;

      if (format == 'xml' && !serviceMetaData) {
        value = value.replace(refcountRegex, '').replace(backpointerRegex, '');
      }
      result.push([ value, highlight ]);
      ({ value, done } = iter.next());

      while (indent > blockIndent && !done) {
        indent = value.replace(indentRegex, '').search(/\S/);
        const backpointerMatch = value.match(backpointerRegex);
        const refcountMatch = value.search(refcountRegex) != -1;
        const isOnlyMeta = ['cli', 'curly-braces'].includes(format) &&
          (refcountMatch || backpointerMatch);

        if (backpointerMatch && !backpointer) {
          backpointer = backpointerMatch[1];
        }

        if (indent == blockIndent) {
          // Only exit statement allowed at same indent
          if (format == 'xml' && value.trim().startsWith(
              '<span class="hljs-tag">&lt;/<span') ||
              ['exit', '!', '}'].includes(value.trim())) {
            result.push([ value, highlight ]);
            ({ value, done } = iter.next());
          }
        } else if (indent > blockIndent) {
          if (isOnlyMeta) {
            if (serviceMetaData) {
              result.push([ value, false ]);
            }
            ({ value, done } = iter.next());
          } else {
            processBlock(backpointer ?
              backpointer.includes(openService) : highlight);
            backpointer = undefined;
          }
        }
      }
    };

    processBlock(false);
    return result;
  }

  btn = (label, selectFormat, tooltip) => {
    const { format, isFetching } = this.state;
    return (
      <InlineBtn
        classSuffix={isFetching ? 'disabled' : (format === selectFormat && 'active')}
        label={label}
        tooltip={tooltip}
        onClick={() => { this.getConfig(selectFormat || format); }}
        align="left"
      />
    );
  };



  render() {
    console.debug('Config Render');
    const { device, managed } = this.props;
    const { format, serviceMetaData, isFetching, config } = this.state;

    return (
      <Accordion
        level="1"
        right={true}
        startOpen={managed}
        variableHeight={true}
        header={<Fragment>
          <span className="config-viewer__title-text">{device}{
            !managed && ' (unmanaged)'}</span>
          {isFetching && <div className="loading__dots">
            <span className="loading__dot"/>
            <span className="loading__dot"/>
            <span className="loading__dot"/>
          </div>}
          <InlineBtn
            type={IconTypes.BTN_GOTO}
            classSuffix="goto"
            tooltip={'View device in Configuration Editor'}
            onClick={(event) => this.goToDevice(event)}
          />
          <InlineBtn
            type={IconTypes.BTN_DEFINE}
            classSuffix="define"
            tooltip={'Define domain on KVM'}
            onClick={(event) => this.libvirtAction(event, 'define')}
          />
          <InlineBtn
            type={IconTypes.BTN_START}
            classSuffix="start"
            tooltip={'Start domain on KVM'}
            onClick={(event) => this.libvirtAction(event, 'start')}
          />
          <InlineBtn
            type={IconTypes.BTN_STOP}
            classSuffix="stop"
            tooltip={'Stop domain on KVM'}
            onClick={(event) => this.libvirtAction(event, 'stop')}
          />
          <InlineBtn
            type={IconTypes.BTN_UNDEFINE}
            classSuffix="undefine"
            tooltip={'Undefine domain on KVM'}
            onClick={(event) => this.libvirtAction(event, 'undefine')}
          />
          <InlineBtn
            type={IconTypes.BTN_RESTART}
            classSuffix="restart"
            tooltip={'Reboot domain on KVM'}
            onClick={(event) => this.libvirtAction(event, 'reboot')}
          />
          <InlineBtn
            type={IconTypes.BTN_RESET}
            classSuffix="hard-reset"
            tooltip={'Hard reset domain on KVM (undefine and restart)'}
            onClick={(event) => this.libvirtAction(event, 'hard-reset')}
          />
        </Fragment>}>
        {managed && <div className="config-viewer__panel">
          <div className="config-viewer__btn-row">
            {this.btn('cli', 'cli', 'Format configuration as Cisco-style CLI')}
            {this.btn('cb', 'curly-braces',
              'Format configuration as Juniper-style curly braces')}
            {this.btn('json', 'json', 'Format configuration as JSON')}
            {this.btn('xml', 'xml', 'Format configuration as XML')}
            {this.btn('yaml', 'yaml', 'Format configuration as YAML')}
            <InlineBtn
              classSuffix={isFetching ? 'disabled' : (serviceMetaData && 'active')}
              label="svc-meta"
              tooltip={`${serviceMetaData ? 'Exclude' :
                'Include'} service meta-data annotations`}
                onClick={() => {
                  this.setState({ serviceMetaData: !serviceMetaData });
                }}
              align="right"
            />
          </div>
          <pre className="config-viewer__pre">
            <code className="config-viewer__code">{
              config !== undefined && format ?
                this.highlightService(hljs.highlight(config, {language: format}).value).map(
                  ([ configLine, highlight ], index) => <div key={index}
                    className={classNames(
                      'config-viewer__line', {
                      'config-viewer__line--highlight': highlight
                    })}
                  dangerouslySetInnerHTML={{ __html: configLine }}
                />)
              : <div>Fetching config...</div>
            }</code>
          </pre>
          <div
            className="loading__overlay"
            style={{ opacity: isFetching | 0 }}
          />
        </div>}
      </Accordion>
    );
  }
}

export default connect(null, mapDispatchToProps)(Config);
