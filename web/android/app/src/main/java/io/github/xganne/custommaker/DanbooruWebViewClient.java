package io.github.xganne.custommaker;

import android.net.Uri;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/**
 * Pedidos ao Danbooru feitos pelo próprio app, e não pelo navegador interno.
 *
 * O Cloudflare do Danbooru barra pedidos feitos por navegador (403 "challenge"),
 * com ou sem login, e também os vindos de servidores (o repassador no Cloudflare
 * Workers foi barrado). Pedidos saindo do celular, identificados como programa,
 * passam — como os do app do PC. Aqui cada GET para o Danbooru (busca,
 * sugestões e imagens, inclusive as das miniaturas) é refeito assim e devolvido
 * à página. Nada do navegador interno é repassado (cookies, cabeçalhos).
 */
public class DanbooruWebViewClient extends BridgeWebViewClient {

    private static final String USER_AGENT = "CustomMakerv2/1.0 (by xGanne on GitHub; Android)";
    private static final int CONNECT_TIMEOUT_MS = 15000;
    private static final int READ_TIMEOUT_MS = 30000;

    public DanbooruWebViewClient(Bridge bridge) {
        super(bridge);
    }

    @Override
    public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
        Uri url = request.getUrl();
        if ("GET".equalsIgnoreCase(request.getMethod()) && isDanbooru(url.getHost())) {
            return fetchNatively(url.toString());
        }
        return super.shouldInterceptRequest(view, request);
    }

    static boolean isDanbooru(String host) {
        return "danbooru.donmai.us".equals(host) || "cdn.donmai.us".equals(host);
    }

    private WebResourceResponse fetchNatively(String url) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(url).openConnection();
            connection.setRequestProperty("User-Agent", USER_AGENT);
            connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
            connection.setReadTimeout(READ_TIMEOUT_MS);
            int status = connection.getResponseCode();
            InputStream body = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            if (body == null) body = new ByteArrayInputStream(new byte[0]);

            String contentType = connection.getContentType();
            String mime = "application/octet-stream";
            String encoding = null;
            if (contentType != null) {
                String[] parts = contentType.split(";");
                mime = parts[0].trim();
                for (String part : parts) {
                    String p = part.trim();
                    if (p.toLowerCase().startsWith("charset=")) encoding = p.substring(8).trim();
                }
            }

            Map<String, String> headers = new HashMap<>();
            // a página (https://localhost) lê a resposta com fetch: libera o CORS
            headers.put("Access-Control-Allow-Origin", "*");
            String cacheControl = connection.getHeaderField("Cache-Control");
            if (cacheControl != null) headers.put("Cache-Control", cacheControl);

            String reason = connection.getResponseMessage();
            if (reason == null || reason.isEmpty()) reason = status < 400 ? "OK" : "Error";
            // o WebResourceResponse lê o corpo depois; a conexão fecha junto com ele
            return new WebResourceResponse(mime, encoding, status, reason, headers, body);
        } catch (IOException error) {
            if (connection != null) connection.disconnect();
            return failure("Sem conexão com o Danbooru: " + error.getMessage());
        }
    }

    /** 502 com a mensagem, liberado para a página mostrar o erro. */
    private static WebResourceResponse failure(String message) {
        Map<String, String> headers = new HashMap<>();
        headers.put("Access-Control-Allow-Origin", "*");
        return new WebResourceResponse(
            "text/plain",
            "utf-8",
            502,
            "Bad Gateway",
            headers,
            new ByteArrayInputStream(message.getBytes(StandardCharsets.UTF_8))
        );
    }
}
