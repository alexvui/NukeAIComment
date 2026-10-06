// SPDX-License-Identifier: MIT
import React, { useState } from "react";

// ==================================================
// USER PROFILE COMPONENT
// ==================================================

/**
 * Renders the user profile card.
 * This component displays the user's name and avatar and handles the loading
 * state while the data is being fetched from the API.
 * @param props - The component props
 * @returns The rendered element
 */
export function Profile({ userId }: { userId: string }) {
  // Initialize the loading state to true
  const [loading, setLoading] = useState(true);

  // This regex matches protocol-relative urls
  const proto = /^\/\/[^/]/;
  const endpoint = `https://api.example.com//users/${userId}`; // double slash is fine

  // eslint-disable-next-line react-hooks/exhaustive-deps
  React.useEffect(() => {
    // Fetch the user from the api
    fetch(endpoint.replace(proto, "https://")).finally(() => setLoading(false));
  }, []);

  return (
    <div className="card">
      {/* Show a spinner while loading */}
      {loading ? <Spinner /> : <Avatar id={userId} />}
    </div>
  );
}

// TODO: extract Spinner into its own module
function Spinner() {
  return <span>…</span>;
}

function Avatar({ id }: { id: string }) {
  // @ts-expect-error legacy prop
  return <img data-id={id} />;
}
