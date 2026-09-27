//const API = "https://slotly-usly.onrender.com";
const API = "https://hair-destination-slotly.duckdns.org";


// ==========================================================
// FCM TOKEN
// ==========================================================

async function saveFcmToken(token) {

    if (!token) {

        console.log(
            "FCM token is empty"
        );

        return;
    }

    try {

        const response = await apiPost(
            "/admin/fcm-token",
            {
                fcm_token: token
            }
        );

        if (response && response.ok) {

            console.log(
                "FCM token saved successfully"
            );

        } else {

            console.error(
                "Failed to save FCM token"
            );
        }

    } catch (err) {

        console.error(
            "FCM token save error:",
            err
        );
    }
}


// ==========================================================
// NATIVE FCM TOKEN BRIDGE
// ==========================================================

window.setNativeFcmToken = function(token) {

    console.log(
        "Native FCM token received"
    );

    if (!token) {

        console.log(
            "Native FCM token is empty"
        );

        return;
    }

    // Store the token until admin authentication
    // is available.
    window.nativeFcmToken = token;

    // If admin is already logged in,
    // save the token immediately.
    if (getToken()) {

        saveFcmToken(token);
    }
};


// ==========================================================
// TOKEN
// ==========================================================

function getToken() {

    return localStorage.getItem("token");
}


// ==========================================================
// AUTH CHECK
// ==========================================================

function requireAuth() {

    const token = getToken();

    if (!token) {

        window.location.href =
            "/admin/login/";

        return false;
    }

    return true;
}


// ==========================================================
// AUTH HEADERS
// ==========================================================

function authHeaders() {

    return {

        "Authorization":
            `Bearer ${getToken()}`
    };
}


// ==========================================================
// LOGOUT
// ==========================================================

function logout() {

    localStorage.removeItem("token");

    window.location.href =
        "/admin/login/";
}


// ==========================================================
// LOGIN
// ==========================================================

async function login() {

    const username =
        document
            .getElementById("username")
            .value
            .trim();

    const password =
        document
            .getElementById("password")
            .value;

    const error =
        document.getElementById("error");

    error.textContent = "";


    if (!username || !password) {

        error.textContent =
            "Please enter username and password.";

        return;
    }


    try {

        const response = await fetch(
            `${API}/auth/login`,
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({
                    username: username,
                    password: password
                })
            }
        );


        const data =
            await response.json();


        if (!response.ok) {

            error.textContent =
                data.detail ||
                "Invalid username or password.";

            return;
        }


        // ==================================================
        // SAVE AUTH TOKEN
        // ==================================================

        localStorage.setItem(
            "token",
            data.access_token
        );


        // ==================================================
        // SAVE FCM TOKEN AFTER SUCCESSFUL LOGIN
        // ==================================================

        // First use the token received from the
        // native Android bridge.

        let fcmToken =
            window.nativeFcmToken;


        // If it is not available yet, ask the
        // native Android bridge directly.

        if (
            !fcmToken &&
            window.SlotlyNative &&
            typeof window.SlotlyNative.getFcmToken === "function"
        ) {

            fcmToken =
                window.SlotlyNative.getFcmToken();
        }


        if (fcmToken) {

            console.log(
                "Saving FCM token after successful login"
            );

            await saveFcmToken(
                fcmToken
            );

        } else {

            console.log(
                "FCM token not available after login"
            );
        }


        // ==================================================
        // REDIRECT
        // ==================================================

        window.location.href =
            "/admin/dashboard/";

    }


    catch (err) {

        console.error(
            "Login error:",
            err
        );

        error.textContent =
            "Unable to connect to server.";
    }
}


// ==========================================================
// API GET
// ==========================================================

async function apiGet(url) {

    const token =
        getToken();

    console.log(
        "GET:",
        `${API}${url}`
    );

    console.log(
        "TOKEN EXISTS:",
        !!token
    );


    const response =
        await fetch(
            `${API}${url}`,
            {
                method: "GET",

                headers: {
                    "Authorization":
                        `Bearer ${token}`
                }
            }
        );


    console.log(
        "API STATUS:",
        response.status
    );


    if (response.status === 401) {

        logout();

        return null;
    }


    if (!response.ok) {

        throw new Error(
            await response.text()
        );
    }


    return await response.json();
}


// ==========================================================
// API POST
// ==========================================================

async function apiPost(url, body) {

    const response =
        await fetch(
            `${API}${url}`,
            {
                method: "POST",

                headers: {

                    "Authorization":
                        `Bearer ${getToken()}`,

                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify(body)
            }
        );


    if (response.status === 401) {

        logout();

        return null;
    }


    return response;
}