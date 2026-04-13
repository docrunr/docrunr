import './utils/console-warn-filters';
import React from 'react';
import ReactDOM from 'react-dom/client';
import './i18n';
import '@mantine/core/styles.css';
import '@mantine/charts/styles.css';
import { createTheme, defaultLoaders, Loader, MantineProvider } from '@mantine/core';
import App from './app/App';
import { RingLoader } from './components/RingLoader';

const theme = createTheme({
  primaryColor: 'dark',
  components: {
    Loader: Loader.extend({
      defaultProps: {
        loaders: { ...defaultLoaders, ring: RingLoader },
        type: 'ring',
        color: 'gray',
      },
    }),
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <App />
    </MantineProvider>
  </React.StrictMode>
);
