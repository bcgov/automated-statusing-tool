import React from "react";
import { useAuth } from '../auth/AuthContext'
import { Button } from "@bcgov/design-system-react-components";


const LoginLogoutButton: React.FC = () => {
  const { user, login, logout, isAuthenticated, isLoadingAuth, roles } = useAuth(); // Added isAuthenticated and isLoadingAuth for clarity

  // Optionally, show nothing or a disabled button if auth status is still loading
  if (isLoadingAuth) {
    return (null); // Or a placeholder, or null
  }

  const hostname = window.location.hostname;
  const isProd = hostname.includes('-prod-');
  const env = isProd ? 'prod' : hostname.includes('-test-') ? 'test' : 'dev';

  const hasViewer = roles?.includes('viewer') ?? false;
  const hasEditor = roles?.includes('editor') ?? false;
  const isRestrictedEnv = env !== 'prod';
  const hasNoAccess = !hasViewer && !hasEditor;

  return (
    <>
      {isAuthenticated ? ( // Or simply 'user' if you prefer checking for user object directly
        <>
        <Button
          onPress={logout}
          variant="secondary"
        >
          Logout ({user?.profile?.name || user?.profile?.email || 'User'}) {/* Display user info if available */}
        </Button>
        </>
      ) : (
        <Button
          onPress={login}
          variant="primary" // Or 'secondary' as in your example
        >
          Login
        </Button>
      )}
    </>
  );
};



export { LoginLogoutButton };