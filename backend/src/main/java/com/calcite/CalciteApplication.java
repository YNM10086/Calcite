package com.calcite;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Calcite 后端启动类。
 *
 * <p>@SpringBootApplication 是三个注解的合体：
 * <ul>
 *   <li>@Configuration       —— 这个类可以作为配置类</li>
 *   <li>@EnableAutoConfiguration —— 让 Spring Boot 按依赖自动装配（比如引入 web 就自动配好 Tomcat）</li>
 *   <li>@ComponentScan       —— 扫描本包及子包下的 @Controller/@Service/@Repository 等</li>
 * </ul>
 *
 * <p>注意：它只扫描 {@code com.calcite} 及其子包，所以自己的代码都要放在这个包下面。
 */
@SpringBootApplication
public class CalciteApplication {

    public static void main(String[] args) {
        SpringApplication.run(CalciteApplication.class, args);
    }
}
