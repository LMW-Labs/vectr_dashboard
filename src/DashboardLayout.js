import React, { useState } from 'react';
import { Box, Drawer, AppBar, Toolbar, Typography, List, ListItem, ListItemButton, ListItemIcon, ListItemText } from '@mui/material';
import DashboardIcon from '@mui/icons-material/Dashboard';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';
import ExploreIcon from '@mui/icons-material/Explore';
import TravelExploreIcon from '@mui/icons-material/TravelExplore';
import SettingsIcon from '@mui/icons-material/Settings';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';

// Import the new page components
import DiscoverSources from './pages/DiscoverSources';
import RunAnalysis from './pages/RunAnalysis';
import ExploreInsights from './pages/ExploreInsights';
import DataUploader from './pages/DataUploader'; // Import DataUploader

const drawerWidth = 240;

const menuItems = [
  { text: 'Dashboard', icon: <DashboardIcon />, component: <Typography>Dashboard Content</Typography> },
  { text: 'Discover Sources', icon: <TravelExploreIcon />, component: <DiscoverSources /> },
  { text: 'Run Analysis', icon: <PlayCircleOutlineIcon />, component: <RunAnalysis /> },
  { text: 'Explore Insights', icon: <ExploreIcon />, component: <ExploreInsights /> },
  { text: 'Data Uploader', icon: <CloudUploadIcon />, component: <DataUploader /> }, // Add DataUploader
  { text: 'Settings', icon: <SettingsIcon />, component: <Typography>Settings Content</Typography> },
];

export default function DashboardLayout() {
  const [selectedComponent, setSelectedComponent] = useState(menuItems[0].component);

  const handleMenuItemClick = (component) => {
    setSelectedComponent(component);
  };

  return (
    <Box sx={{ display: 'flex' }}>
       <div style={{
          position: 'fixed', // Changed to fixed for viewport centering
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          opacity: 0.1, 
          pointerEvents: 'none', 
          zIndex: -1,
        }}>
          <img src="/V.png" alt="V Backdrop" style={{ height: '50vh' }} />
        </div>

      <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1, background: 'transparent', boxShadow: 'none' }}>
        <Toolbar>
          <img src="/VECTR.png" alt="Vectr Logo" style={{ height: '40px' }} />
        </Toolbar>
      </AppBar>

      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: 'border-box', background: 'rgba(0,0,0,0.2)' }, 
        }}
      >
        <Toolbar />
        <Box sx={{ overflow: 'auto' }}>
          <List>
            {menuItems.map((item) => (
              <ListItem key={item.text} disablePadding onClick={() => handleMenuItemClick(item.component)}>
                <ListItemButton>
                  <ListItemIcon sx={{ color: '#FFF' }}>{item.icon}</ListItemIcon>
                  <ListItemText primary={item.text} />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
        </Box>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        <Toolbar />
        {selectedComponent}
      </Box>
    </Box>
  );
}
