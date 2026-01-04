package com.example.demo;

import org.springframework.web.bind.annotation.*;

/**
 * 示例控制器
 */
@RestController
@RequestMapping("/api")
public class Example {
    
    /**
     * 获取问候消息
     * @param name 名称
     * @return 问候消息
     */
    @GetMapping("/hello")
    public String hello(@RequestParam String name) {
        return "Hello, " + name;
    }
    
    /**
     * 创建用户
     */
    @PostMapping("/user")
    @Transactional
    public void createUser(@RequestBody User user) {
        // 创建用户逻辑
        System.out.println("Creating user: " + user.getName());
    }
}
